#!/usr/bin/env bash

NODE_PATTERN="rft-node"
NET_PATTERN="rft-net"
WORKDIR="/tmp/ramdisk-func-test"

for node in $(virsh list --all | awk '{print $2}' | grep $NODE_PATTERN);
do
virsh destroy $node;
virsh undefine $node;
done

for net in $(virsh net-list --all | awk '{print $1}' | grep $NET_PATTERN);
do
virsh net-destroy $net;
virsh net-undefine $net;
done

sudo rm -rf $WORKDIR

# TODO: clean webserver daemons

