# OPNsense NordVPN Client Updater

A script to automatically update OPNsense VPN client configurations with optimal NordVPN servers.

## Features

- Supports both OpenVPN and WireGuard configurations
- Command-line options to update specific VPN types
- Automatically finds optimal server based on country, group, and technology
- Restarts services after configuration updates
- Maintains backup of configuration files

## Setup

1. Copy the `update_vpn_clients.py` and `actions_nordvpn.conf` files to somewhere on your system, like your home folder
2. Make the script executable: `chmod +x update_vpn_clients.py`
3. Note the absolute path of the .py file (needed for the cron step)

## Configuration

### VPN Client Settings

1. Open the python file and look for the `openvpn_list` and `wireguard_list` variables
2. Change the "target" fields to match your existing OPNsense VPN client names
3. Modify the other fields to your requirements:
   - For countries (use ID values): https://github.com/azinchen/nordvpn/blob/master/COUNTRIES.md
   - For groups (use identifier values): https://github.com/azinchen/nordvpn/blob/master/GROUPS.md
   - For technologies (use identifier values): https://github.com/azinchen/nordvpn/blob/master/TECHNOLOGIES.md
   - You can add/remove more objects to the arrays, depending on your needs
4. Save the file

### Configuration Notes

- For OpenVPN clients, ensure the description in OPNsense matches the "target" field
- For WireGuard clients, ensure the name in OPNsense matches the "target" field
- The script will only update and restart VPN clients that already exist in your configuration

## OPNsense Integration

1. Open `actions_nordvpn.conf` and update all the "parameters" fields with the absolute path of the .py file
2. Copy `actions_nordvpn.conf` to the `/usr/local/opnsense/service/conf/actions.d` folder
3. Run `sudo service configd restart` to apply the changes

## Testing

Run one of the following commands to test:

```bash
# Update only OpenVPN clients
sudo configctl nordvpn openvpn

# Update only WireGuard clients
sudo configctl nordvpn wireguard

# Update all clients
sudo configctl nordvpn all
```

The command should return "OK". If not:

- Make sure the paths in the .conf file are correct
- Try to manually execute the script to see what is wrong
- Manual execution example: `sudo /usr/local/bin/python3 /home/admin/vpn/update_vpn_clients.py --type all`

## Debugging

- Add `--verbose` to the command line for more detailed output
- You can also change the "type" value in the .conf file to "script_output" for more verbose logs

## Automation

If everything is working correctly, you can create a cron entry in the OPNsense GUI to run the updater regularly.
