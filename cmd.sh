#!/bin/bash
# Remove duplicate/broken fstab entries
sudo sed -i '/192.168.1.1\/H/d' /etc/fstab

# Add corrected entry with SMB version
echo '//192.168.1.1/H /mnt/downloads cifs credentials=/etc/smbcredentials,uid=1000,gid=1000,iocharset=utf8,vers=2.0 0 0' | sudo tee -a /etc/fstab

# Reload systemd and mount
sudo systemctl daemon-reload
sudo mount -a

# Verify
df -h | grep downloads
