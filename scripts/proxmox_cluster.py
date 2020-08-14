#!/usr/bin/python3

# -*- coding: utf-8 -*-
"""Report Proxmox cluster statistics to Zabbix.

Copyright (C) 2020 Takala Consulting

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

Minimum requirements Proxmox 5, Python 3.4, Zabbix 3.0.
"""

__version__ = '0.0.3'

# Import modules
import argparse
import yaml
import json
import re
import socket
import sys
import subprocess
import time
from proxmoxer import ProxmoxAPI

# Set up argument parser
parser = argparse.ArgumentParser(
    description='Report Proxmox cluster statistics to zabbix')
# Add optional arguments to the parser
parser.add_argument('-a',
                    '--apihost',
                    default='localhost',
                    help='Proxmox API hostname')
parser.add_argument('-c',
                    '--config',
                    default='/etc/zabbix/zabbix_agentd.conf',
                    help='full path to zabbix_agentd configuration file')
parser.add_argument('-C',
                    '--config-proxmox-cluster',
                    default=None,
                    help='full path to proxmox_cluster.yml configuration file')
parser.add_argument('-d',
                    '--discovery',
                    help='send low level discovery data instead of items',
                    action="store_true")
parser.add_argument('-e',
                    '--extended',
                    help='get extended configuration to return vHDD allocation',
                    action="store_true")
parser.add_argument('-p',
                    '--password',
                    default='',
                    help='Proxmox API password')
parser.add_argument('-t',
                    '--target',
                    default=socket.gethostname(),
                    help='zabbix target hostname')
parser.add_argument('-u',
                    '--username',
                    default='zabbix@pve',
                    help='Proxmox API username')
parser.add_argument('-v',
                    '--verbose',
                    help='output verbose discovery and item data',
                    action="store_true")
parser.add_argument('-z',
                    '--zsend',
                    default='/usr/bin/zabbix_sender',
                    help='full path to zabbix sender binary')

# Parse the arguments
args = parser.parse_args()

if args.config_proxmox_cluster:
    with open(args.config_proxmox_cluster, 'r', encoding='utf8') as fp:
        y = yaml.load(fp, Loader=yaml.SafeLoader)
        if y['target'] == 'socket.gethostname()':
            y['target'] = socket.gethostname()

        class dict_to_obj(object):
            def __init__(self, d):
                self.__dict__ = d
            # def __repr__(self):
            #     keys = sorted(self.__dict__)
            #     items = ("{}={!r}".format(k, self.__dict__[k]) for k in keys)
            #     return "{}({})".format(type(self).__name__, ", ".join(items))
        yargs = dict_to_obj(y)

        if args.extended:
            yargs.extended = args.extended
        if args.verbose:
            yargs.verbose = args.verbose
        args = yargs

# connect to Proxmox API
try:
    proxmox = ProxmoxAPI(args.apihost,
                         user=args.username,
                         password=args.password,
                         verify_ssl=False)
except Exception as error:  # pylint: disable=broad-except
    print("Proxmox API call failed:", str(error))
    sys.exit(1)

# base dictionary for cluster data
cluster_data = {
    'status': {
        'quorate': 0,
        'cpu_total': 0,
        'cpu_usage': 0,
        'ram_total': 0,
        'ram_used': 0,
        'ram_free': 0,
        'ram_usage': 0,
        'ksm_sharing': 0,
        'vcpu_allocated': 0,
        'vram_allocated': 0,
        'vhdd_allocated': 0,
        'vram_used': 0,
        'vram_usage': 0,
        'vms_running': 0,
        'vms_stopped': 0,
        'vms_total': 0,
        'lxc_running': 0,
        'lxc_stopped': 0,
        'lxc_total': 0,
        'vm_templates': 0,
        'nodes_total': 0,
        'nodes_online': 0,
    },
    'nodes': {}
}

# get cluster and nodes overview
for node in proxmox.cluster.status.get():
    if node['type'] == "cluster":
        cluster_data['status']['quorate'] = node['quorate']
        cluster_data['status']['nodes_total'] = node['nodes']
    if node['type'] == "node":
        cluster_data['nodes'][node['name']] = {
            'online': node['online'],
            'vms_total': 0,
            'vms_running': 0,
            'lxc_total': 0,
            'lxc_running': 0,
            'vcpu_allocated': 0,
            'vram_allocated': 0,
            'vhdd_allocated': 0,
            'vram_used': 0,
            'ksm_sharing': 0,
        }

# if requested send low level discovery data now and exit
if args.discovery:
    discovery_data = (json.dumps(
        {'data': [{
            "{#NODE}": n
        } for n in cluster_data['nodes']]}))
    if args.verbose:
        print(discovery_data)
    try:
        result = subprocess.check_output([
            args.zsend, "-c" + args.config, "-s" + args.target,
            "-k" + "proxmox.nodes.discovery", "-o" + str(discovery_data)
        ])
    except Exception as error:  # pylint: disable=broad-except
        print("Error while sending discovery data:", str(error))
        sys.exit(1)
    if args.verbose:
        print(result)
    sys.exit(0)

# get cluster and node details
for node in proxmox.nodes.get():
    if node['type'] == "node":
        cluster_data['nodes'][node['node']]['cpu_total'] = node.get(
            'maxcpu', 0)
        cluster_data['nodes'][node['node']]['cpu_usage'] = node.get(
            'cpu', 0) * 100
        cluster_data['nodes'][node['node']]['ram_total'] = node.get(
            'maxmem', 0)
        cluster_data['nodes'][node['node']]['ram_used'] = node.get(
            'mem', 0)
        cluster_data['nodes'][node['node']]['ram_free'] = node.get(
            'maxmem', 0) - node.get('mem', 0)
        cluster_data['nodes'][node['node']]['ram_usage'] = 100 * (
            float(node.get('mem', 0)) / float(node.get('maxmem', 1)))
        # update cluster total metrics
        cluster_data['status']['cpu_total'] += node.get('maxcpu', 0)
        cluster_data['status']['ram_total'] += node.get('maxmem', 0)
        cluster_data['status']['ram_used'] += node.get('mem', 0)
        cluster_data['status']['ram_free'] += node.get(
            'maxmem', 0) - node.get('mem', 0)

# update cluster total ram usage percentage
if float(cluster_data['status']['ram_total']) > 0:
    cluster_data['status']['ram_usage'] = 100 * (
        float(cluster_data['status']['ram_used']) /
        float(cluster_data['status']['ram_total']))

# get ksm sharing and cpu usage info from online nodes
cpu_usage_combined = 0
for n in cluster_data['nodes']:
    if cluster_data['nodes'][n]['online'] == 1:
        cluster_data['status']['nodes_online'] += 1
        cpu_usage_combined += cluster_data['nodes'][n]['cpu_usage']
        node_status = proxmox.nodes(n).status.get()
        cluster_data['status']['ksm_sharing'] += node_status['ksm'].get(
            'shared', 0)
        cluster_data['nodes'][n]['ksm_sharing'] += node_status['ksm'].get(
            'shared', 0)

# calculate cluster total cpu usage percentage
if float(cluster_data['status']['nodes_online']) > 0:
    cluster_data['status']['cpu_usage'] = (
        float(cpu_usage_combined) / float(cluster_data['status']['nodes_online']))

# regular expression to match disk strings in vm config
disk_pattern = re.compile(r"vm-\d+-disk-\d+")
# regular expression to match size block in config string
size_pattern = re.compile(r"^size=\d+[T|G|M|K]")
# regular expression to match G in config block
gig_pattern = re.compile(r"^\d+G$")


def update_vhdd(config, target):
    """Get the HDD size from a configuration file string and update cluster stats.

    Data is stored in bytes to allow better representation in the zabbix UI.
    The G quantifier is using a compiled re, and placed first, as it typically
    matches the vast majority of cases.
    """
    for item in config.split(','):
        if size_pattern.search(item):
            size = item.split('=')[1]
            if gig_pattern.search(size):
                cluster_data['status']['vhdd_allocated'] += 1073741824 * int(
                    size.replace('G', ''))
                cluster_data['nodes'][target]['vhdd_allocated'] += 1073741824 * int(
                    size.replace('G', ''))
            elif re.search(r"^\d+K$", size):
                cluster_data['status']['vhdd_allocated'] += 1024 * int(
                    size.replace('K', ''))
                cluster_data['nodes'][target]['vhdd_allocated'] += 1024 * int(
                    size.replace('K', ''))
            elif re.search(r"^\d+M$", size):
                cluster_data['status']['vhdd_allocated'] += 1048576 * int(
                    size.replace('M', ''))
                cluster_data['nodes'][target]['vhdd_allocated'] += 1048576 * int(
                    size.replace('M', ''))
            elif re.search(r"^\d+T$", size):
                cluster_data['status']['vhdd_allocated'] += 1099511627776 * int(
                    size.replace('T', ''))
                cluster_data['nodes'][target]['vhdd_allocated'] += 1099511627776 * int(
                    size.replace('T', ''))


# get vm details
for vm in proxmox.cluster.resources.get(type='vm'):
    # if status is unknown we can't get details
    if vm.get('status', 'unknown') == 'unknown':
        continue
    # if this is a template we only count it
    if vm.get('template', 0) == 1:
        cluster_data['status']['vm_templates'] += 1
        continue
    # update cluster total metrics
    cluster_data['status']['vcpu_allocated'] += vm.get('maxcpu', 0)
    cluster_data['status']['vram_allocated'] += vm.get('maxmem', 0)
    cluster_data['status']['vram_used'] += vm.get('mem', 0)
    # update individual node metrics
    cluster_data['nodes'][vm['node']]['vcpu_allocated'] += vm.get('maxcpu', 0)
    cluster_data['nodes'][vm['node']]['vram_allocated'] += vm.get('maxmem', 0)
    cluster_data['nodes'][vm['node']]['vram_used'] += vm.get('mem', 0)
    # if this is a qemu vm
    if vm.get('type', 'unknown') == 'qemu':
        cluster_data['status']['vms_total'] += 1
        cluster_data['nodes'][vm['node']]['vms_total'] += 1
        # count number of running VMs
        if vm.get('status', 'unknown') == 'running':
            cluster_data['status']['vms_running'] += 1
            cluster_data['nodes'][vm['node']]['vms_running'] += 1
        if args.extended:
            # get vm configuration details
            vm_config = proxmox.nodes(vm['node']).qemu(vm['vmid']).config.get()
            for c in vm_config:
                if disk_pattern.search(str(vm_config.get(c))):
                    update_vhdd(vm_config.get(c), vm['node'])
    # if this is a lxc container
    if vm.get('type', 'unknown') == 'lxc':
        cluster_data['status']['lxc_total'] += 1
        cluster_data['nodes'][vm['node']]['lxc_total'] += 1
        # count number of running containers
        if vm.get('status', 'unknown') == 'running':
            cluster_data['status']['lxc_running'] += 1
            cluster_data['nodes'][vm['node']]['lxc_running'] += 1
        if args.extended:
            # get container configuration details
            vm_config = proxmox.nodes(vm['node']).lxc(vm['vmid']).config.get()
            for c in vm_config:
                if disk_pattern.search(str(vm_config.get(c))):
                    update_vhdd(vm_config.get(c), vm['node'])

# calculate cluster total vram usage percentage
if float(cluster_data['status']['vram_allocated']) > 0:
    cluster_data['status']['vram_usage'] = 100 * (
        float(cluster_data['status']['vram_used']) /
        float(cluster_data['status']['vram_allocated']))

# calculate cluster total VMs stopped
cluster_data['status']['vms_stopped'] = (cluster_data['status']['vms_total'] -
                                         cluster_data['status']['vms_running'])

# calculate cluster total containers stopped
cluster_data['status']['lxc_stopped'] = (cluster_data['status']['lxc_total'] -
                                         cluster_data['status']['lxc_running'])

if args.verbose:
    print(json.dumps(cluster_data, indent=4))

# Prepare values for zabbix
epoch_seconds = int(time.time())
item_data = ''
for s in cluster_data['status']:
    item_data += (args.target + " " + "promox.cluster." + str(s) + " " +
                  str(epoch_seconds) + " " + str(cluster_data['status'][s]) +
                  "\r\n")
for n in cluster_data['nodes']:
    for i in cluster_data['nodes'][n]:
        item_data += (args.target + " " + "proxmox.node." + str(i) + ".[" +
                      str(n) + "]" + " " + str(epoch_seconds) + " " +
                      str(cluster_data['nodes'][n][i]) + "\r\n")

if args.verbose:
    print(item_data)

# send item values
try:
    zabbix_sender = subprocess.Popen(
        [args.zsend, "-c" + args.config, "-T", "-i", "-"],
        stdout=subprocess.PIPE,
        stdin=subprocess.PIPE)
except Exception as error:  # pylint: disable=broad-except
    print("Unable to open zabbix_sender:", str(error))
    sys.exit(1)
try:
    result = zabbix_sender.communicate(bytes(item_data, 'UTF-8'))
except Exception as error:  # pylint: disable=broad-except
    print("Error while sending values:", str(error))
    sys.exit(1)
if args.verbose:
    print(result)

# Sayonara
sys.exit(0)
