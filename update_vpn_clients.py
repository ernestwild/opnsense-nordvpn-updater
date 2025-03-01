#!/usr/bin/env python3

from xml.etree import ElementTree
from shutil import copy
from urllib.request import urlopen
from urllib.parse import urlencode
import json
import os
import argparse
import sys
import time

# Paths
config_path = "/conf/config.xml"
config_backup_path = "/conf/config.xml.bak"

# VPN settings for OpenVPN
openvpn_list = [
    {
        "target": "NordVPN Main",
        "port": "1194",
        "country": "81",
        "group": "legacy_standard",
        "technology": "openvpn_udp"
    },
    {
        "target": "NordVPN Fallback",
        "port": "443",
        "country": "81",
        "group": "legacy_standard",
        "technology": "openvpn_tcp"
    }
]

# VPN settings for WireGuard
wireguard_list = [
    {
        "target": "nordlynx1",
        "port": "51820",
        "country": "81",
        "group": "legacy_standard"
    }
]

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Update OPNsense VPN clients with NordVPN servers.')
    parser.add_argument('--type', choices=['openvpn', 'wireguard', 'all'], default='openvpn',
                        help='VPN type to update (openvpn, wireguard, or all)')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--debug-xml', action='store_true', help='Print XML structure to help with debugging')
    return parser.parse_args()

def log(message, verbose_only=False, args=None):
    """Log messages based on verbosity settings."""
    if not verbose_only or (args and args.verbose):
        print(message)

def get_optimal_server(country, group, technology, exclude_ip):
    """Request optimal VPN server from NordVPN API."""
    
    # Build request parameters
    params = {
        "filters[country_id]": country,
        "limit": 3
    }
    
    # Add group filter if provided
    if group:
        params["filters[servers_groups][identifier]"] = group
    
    # Add technology filter if provided
    if technology:
        params["filters[servers_technologies][identifier]"] = technology
    
    # Perform request
    selected_server = None
    
    try:
        request = urlopen("https://api.nordvpn.com/v1/servers/recommendations?" + urlencode(params))
        response = request.read()
        
        # Parse result & get best server
        parsed_response = json.loads(response)
        
        for server in parsed_response:
            server_ip = server.get("station")
            
            # Exclusion check
            if server_ip != exclude_ip:
                # For WireGuard, we need more than just the IP
                if technology == "wireguard_udp":
                    # Extract public key from technologies array
                    public_key = ""
                    # Look for wireguard_udp technology and its metadata
                    for tech in server.get("technologies", []):
                        if tech.get("identifier") == "wireguard_udp":
                            # Look for public_key in metadata
                            for meta in tech.get("metadata", []):
                                if meta.get("name") == "public_key":
                                    public_key = meta.get("value", "")
                                    break
                            break
                    
                    # Get server details including public key
                    selected_server = {
                        "ip": server_ip,
                        "public_key": public_key,
                        "name": server.get("name", "")
                    }
                else:
                    # For OpenVPN, just return the IP address
                    selected_server = {"ip": server_ip}
                break
                
    except Exception as e:
        print(f"API request failed: {str(e)}")
    
    # Return result
    return selected_server

def update_openvpn_clients(root, args):
    """Update OpenVPN client configurations."""
    last_server = None
    vpn_id_list = []
    
    log("Updating OpenVPN clients...", args=args)
    
    # Go through VPN list to update entries
    for item in openvpn_list:
        target_desc = item.get("target")
        log(f"Processing OpenVPN client: {target_desc}", args=args)
        
        # Try to find config entry
        xpath = f"./openvpn/openvpn-client/[description='{target_desc}']"
        entry = root.find(xpath)
        
        if entry is None:
            log(f"Client entry not found for {target_desc}, skipping...", args=args)
            continue
        
        # Request optimal VPN server from API
        last_ip = None if last_server is None else last_server.get("ip")
        server_info = get_optimal_server(
            item.get("country"), 
            item.get("group"), 
            item.get("technology"), 
            last_ip
        )
        
        # When server info is received, update values
        if server_info is not None:
            last_server = server_info
            server_ip = server_info.get("ip")
            log(f"Found optimal server: {server_ip}", verbose_only=True, args=args)
            
            server_addr_elem = entry.find("server_addr")
            server_port_elem = entry.find("server_port")
            
            if server_addr_elem is not None:
                server_addr_elem.text = server_ip
            
            if server_port_elem is not None:
                server_port_elem.text = item.get("port")
            
            # Also mark VPN client for restart
            vpn_id_elem = entry.find("vpnid")
            if vpn_id_elem is not None:
                vpn_id_list.append(vpn_id_elem.text)
    
    return vpn_id_list

def update_wireguard_clients(root, args):
    """Update WireGuard client configurations."""
    last_server = None
    vpn_id_list = []
    
    log("Updating WireGuard clients...", args=args)
    
    # Go through WireGuard list to update entries
    for item in wireguard_list:
        target_desc = item.get("target")
        log(f"Processing WireGuard client: {target_desc}", args=args)
        
        # Try different possible XPath patterns for finding WireGuard clients
        possible_xpaths = [
            f"./OPNsense/wireguard/client/clients/client/[name='{target_desc}']"
        ]
        
        entry = None
        used_xpath = None
        
        # Try each possible XPath until we find a match
        for xpath in possible_xpaths:
            entry = root.find(xpath)
            if entry is not None:
                used_xpath = xpath
                log(f"Found client using XPath: {xpath}", verbose_only=True, args=args)
                break
        
        if entry is None:
            # Try one more approach - search all client elements for matching name
            all_clients = root.findall(".//client")
            for client in all_clients:
                name_elem = client.find("name")
                if name_elem is not None and name_elem.text == target_desc:
                    entry = client
                    log(f"Found client using general search", verbose_only=True, args=args)
                    break
        
        if entry is None:
            log(f"Client entry not found for {target_desc}, skipping...", args=args)
            continue
        
        # Request optimal VPN server from API
        last_ip = None if last_server is None else last_server.get("ip")
        server_info = get_optimal_server(
            item.get("country"), 
            item.get("group"), 
            "wireguard_udp",  # Ensure we're using WireGuard tech type
            last_ip
        )
        
        # When server info is received, update values
        if server_info is not None:
            last_server = server_info
            server_ip = server_info.get("ip")
            public_key = server_info.get("public_key", "")
            
            log(f"Found optimal WireGuard server: {server_ip}", verbose_only=True, args=args)

            # Update server address (not endpoint)
            address_elem = entry.find("serveraddress")
            if address_elem is not None:
                address_elem.text = server_ip

            # Update public key
            pubkey_elem = entry.find("pubkey")
            if pubkey_elem is not None and public_key:
                pubkey_elem.text = public_key
                log(f"Updated public key: {public_key}", verbose_only=True, args=args)
            elif public_key:
                log(f"Public key element not found, but received key: {public_key}", args=args)
            
            # Also mark WireGuard client for restart
            # UUID is an attribute on the client node, not a child element
            wg_id = entry.get("uuid")
            if wg_id is not None:
                vpn_id_list.append(wg_id)
            else:
                log(f"Could not find UUID attribute for WireGuard client: {target_desc}", args=args)
    
    return vpn_id_list

def restart_openvpn_services(vpn_id_list, args):
    """Restart OpenVPN services for updated clients."""
    if not vpn_id_list:
        return
    
    log("Restarting OpenVPN services...", args=args)
    for vpn_id in vpn_id_list:
        log(f"Restarting OpenVPN with ID {vpn_id}...", args=args)
        os.system(f"pluginctl -s openvpn restart {vpn_id}")
        time.sleep(1)  # Give some time between restarts

def restart_wireguard_services(vpn_id_list, args):
    """Restart WireGuard services for updated clients."""
    if not vpn_id_list:
        return
    
    log("Restarting WireGuard services...", args=args)
    # Restart the entire WireGuard service since individual restart isn't typically available
    os.system("pluginctl -s wireguard restart")

def run():
    """Main execution function."""
    args = parse_arguments()
    
    # Make copy of config file
    if os.path.exists(config_path):
        copy(config_path, config_backup_path)
        log("Created backup of config file", args=args)
    else:
        log("Config file not found, stopping...")
        return 1

    # Load config file
    tree = ElementTree.parse(config_backup_path)
    root = tree.getroot()
    
    # Debug XML structure if debug-xml flag is enabled
    if args and args.debug_xml:
        log("XML structure for debugging:", args=args)
        # Look for WireGuard-related elements
        wireguard_elements = []
        for elem in root.iter():
            if "wireguard" in elem.tag:
                wireguard_elements.append(elem)
                
        if wireguard_elements:
            log("Found WireGuard elements in config:", args=args)
            for elem in wireguard_elements:
                # Print element and its children
                log(f"Element: {elem.tag}", args=args)
                for child in elem:
                    log(f"  - Child: {child.tag}", args=args)
                    # If this is a clients container, show structure
                    if child.tag == "clients" or child.tag == "client":
                        for subchild in child:
                            log(f"    - Subchild: {subchild.tag}", args=args)
                            if subchild.tag == "client":
                                name = subchild.find("name")
                                name_text = name.text if name is not None else "unknown"
                                log(f"      - Client name: {name_text}", args=args)
        else:
            log("No WireGuard elements found in config", args=args)
    
    openvpn_ids = []
    wireguard_ids = []
    
    # Process OpenVPN clients if requested
    if args.type in ['openvpn', 'all']:
        openvpn_ids = update_openvpn_clients(root, args)
    
    # Process WireGuard clients if requested
    if args.type in ['wireguard', 'all']:
        wireguard_ids = update_wireguard_clients(root, args)
    
    # Prevent further action if no VPN is marked
    if not openvpn_ids and not wireguard_ids:
        log("Nothing to do, stopping...")
        return 0
    
    # Save config
    tree.write(config_path)
    log("Config has been updated!")
    
    # Restart services
    if openvpn_ids:
        restart_openvpn_services(openvpn_ids, args)
    
    if wireguard_ids:
        restart_wireguard_services(wireguard_ids, args)
    
    return 0

if __name__ == "__main__":
    sys.exit(run())