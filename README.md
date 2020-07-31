# Monitor a Proxmox cluster with Zabbix

Get cluster and node details from the Proxmox API and report them to Zabbix using zabbix_sender.

## Features

  * Low Level Discovery of cluster nodes
  * Collects cluster quorum and nodes status, overall cluster and nodes RAM/CPU usage and KSM sharing, vRAM allocation and usage, vCPU and vHDD allocations, number of VMs and LXC containers running or stopped.

## Installation

The script can run on any host with Python, a functional zabbix_sender and access to the Proxmox API. A Zabbix server or Zabbix proxy would be logical candidates.

  * Install Python proxmoxer: `pip install proxmoxer`
  * Install Python requests: `pip install requests`
  * Copy script **scripts/proxmox_cluster.py** and make it executable. The script is executed from cron or systemd timers and can be placed anywhere logical.
  * Import the valuemap **templates/snmp_boolean_type_valuemap.xml** into your Zabbix server. This valuemap is used to display quorum and nodes online status.
  * Import the template **templates/proxmox_cluster_template.xml** into your Zabbix server.
  * Create a Proxmox host in Zabbix. This is not an actual server but represents the whole cluster.
  * Attach the template *Template Proxmox cluster* to the host.
  * Create a zabbix user in Proxmox: `pveum useradd zabbix@pve -comment "Zabbix monitoring user"`
  * Set a password for the zabbix user in Proxmox: `pveum passwd zabbix@pve`
  * Grant read only permissions to the zabbix user. The built in **PVEAuditor** role seems a good choice: `pveum aclmod / -user zabbix@pve -role PVEAuditor`
  * Set up scheduled tasks executing the script. The following two examples use cron: `crontab -e -u zabbix`
    * Send discovery data: `0 */4 * * * /usr/lib/zabbix/bin/proxmox_cluster.py -a pmx01.your.tld -u zabbix@pve -p password -t proxmox.tokyo.prod -d`
    * Send item data: `*/10 * * * * /usr/lib/zabbix/bin/proxmox_cluster.py -a pmx01.your.tld -u zabbix@pve -p password -t proxmox.tokyo.prod`

## Configuration

The script accepts the following parameters:

  * -a : Proxmox API hostname or IP address (can include port if the API listens on a non default port, e.g. pmx01.your.tld:8443)
  * -c : Zabbix agent configuration file that is passed as a parameter to zabbix sender (defaults to: */etc/zabbix/zabbix_agentd.conf*)
  * -d : Send discovery data instead of item data
  * -e : Get extended VM configuration details in order to collect vHDD allocations (see notes)
  * -p : Proxmox API password
  * -t : Zabbix target host name (the host in Zabbix with the *Template Proxmox cluster* template attached)
  * -u : Proxmox API username (defaults to: *zabbix@pve*)
  * -v : Verbose, prints data and zabbix_sender results to stdout.
  * -z : Full path to zabbix_sender (defaults to */usr/bin/zabbix_sender*)

## Notes

Getting all vHDD information requires parsing the full VM configuration. That results in one additional API call for each VM to retrieve the configuration. Subsequent processing relies heavily on regular expressions. As this is an expensive process it is optional and can be enabled by specifying -e on the command line.

Resources allocated to templates are not included in the total vCPU, vHDD and vRAM numbers reported to zabbix.

If there is no load balancer fronting the API it would make sense to use multiple scheduled tasks using different Proxmox servers. This would distribute the load and ensure Zabbix remains updated during maintenance or downtime of a host. An example using cron would look as follows:

```
# Item updates every 10 minutes
0,20,40 * * * * /usr/lib/zabbix/bin/proxmox_cluster.py -a pmx01.your.tld -u zabbix@pve -p password -t proxmox.tokyo.prod
10,30,50 * * * * /usr/lib/zabbix/bin/proxmox_cluster.py -a pmx02.your.tld -u zabbix@pve -p password -t proxmox.tokyo.prod
# LLD updates every 4 hours
23 0,8,16 * * * /usr/lib/zabbix/bin/proxmox_cluster.py -a pmx01.your.tld -u zabbix@pve -p password -t proxmox.tokyo.prod -d
38 4,12,20 * * * /usr/lib/zabbix/bin/proxmox_cluster.py -a pmx02.your.tld -u zabbix@pve -p password -t proxmox.tokyo.prod -d 
```

One of the zabbix item keys in the script, and template, is prefixed ```promox```. That is obviously a typo but changing it would mean breaking compatability with existing installations. Changing the key in zabbix would mean losing historical data which is also undesirable. This is purely a cosmetic issue but if desirable you can of course change the prefix for those items. In that case also make sure that the keys in the template are updated accordingly.

If you define the zabbix monitor user in Linux instead of Proxmox the -u parameter would have to reflect that by using the pam realm: ```zabbix@pam```.

Minimum requirements Proxmox 5, Python 3.4 and Zabbix 3.0.

Verified against Proxmox 6, Python 3.6 and Zabbix 5.0.

## Issues

The first step when diagnosing issues is to ensure that zabbix_sender is working and the target host in zabbix is configured correctly. Try the following command on the host where the script is going to run. This should return "processed: 1; failed: 0":

```
[user@zabbix ~]# /usr/bin/zabbix_sender -v -c /etc/zabbix/zabbix_agentd.conf -s proxmox.tokyo.prod -k promox.cluster.quorate -o 1
Response from "127.0.0.1:10051": "processed: 1; failed: 0; total: 1; seconds spent: 0.000036"
sent: 1; skipped: 0; total: 1
```

The value for the -s parameter is the host you configured in the zabbix GUI to receive the data and attached the template to. That is the value you should use for the -t parameter with the script. (please note that the key value of the -k parameter is currently indeed promox.cluster.quorate an unfortunate typo mentioned under notes as well).

## License

This software is licensed under GNU General Public License v3.0
