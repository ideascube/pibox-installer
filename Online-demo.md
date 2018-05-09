Online Image Demo
===

For testing purpose, we want to provide access to generated images online. While it does not allow one to test all the features (WiFi, captive-portal, etc), it helps figuring out the content and the branding.

# How it works?

Qemu's default network stack is limited and has poor performances. In order to expose the VM's web server, we need to create a virtual network card on the host, attach it to Qemu and proxy the VM's web server.

* create a TAP (tunnel) interface for qemu
* create a bridge interface on the host and attach the tap one to it
* set a private IP to the bridge (`192.168.1.1`)
* add an nginx vhost with `proxy_pass http://192.168.1.3`
* start the image with `-netdev tap` to attach the TAP to the VM
 * set a static IP (`192.168.1.3`) on the tap (`eth0` in the VM) on the same network.
 * add host (bridge) IP to the cleared list of captive portal (iptables)
 * remove the cron task which clears that list periodically
 * run the ansible playbook with `rename` tag to configure for `demo.kiwix.ml`

# Setup

**warning**: the following scripts assumes:

* internet on host is on `eth0`
* host is not using private network `192.168.1.0/24`
* dedicated user will be `qdemo`
* host is a (deb-friendly) `x86_64`
* host is not already using `tap0` nor `br0`
* host is not already using port `5022`
* test domain (`demo.kiwix.ml` and subdomains point to host)

``` sh
# install dependency
apt install -y uml-utilities

# download static qemu (linux64)  -- requires qemu 2.8+
wget https://kiwix.ml/qemu-2.12.0-linux-x86_64.tar.gz
tar xf qemu-*.tar.gz
mv qemu-{system-arm,img} /usr/local/bin/

# create dedicated user
useradd -g www-data -l -m -N -s /bin/bash qdemo

# add fake domains to hosts to be able to test outside nginx
echo "192.168.1.3        ideascube.lan demo.kiwix.ml kiwix.demo.kiwix.ml khanacademy.demo.kiwix.ml aflatoun.demo.kiwix.ml edupi.demo.kiwix.ml wikifundi.demo.kiwix.ml sites.demo.kiwix.ml demo kiwix.dem    ↪ o khanacademy.demo aflatoun.demo edupi.demo wikifundi.demo sites.demo" >> /etc/hosts

# download and execute at-boot script
wget https://kiwix.ml/demo/host-setup.sh -O /root/host-setup.sh && sh /root/host-setup.sh

# add cron task for this script
echo "@reboot /root/host-setup.sh" >> /etc/crontab

# download and install nginx vhost
wget https://kiwix.ml/demo/nginx-vhost -O /etc/nginx/sites-available/demo.kiwix.ml
ln -s /etc/nginx/sites-available/https://kiwix.ml/demo/nginx-vhost /etc/nginx/sites-enabled/demo.kiwix.ml
nginx -s reload

# download and install qemu-shortcut
wget https://kiwix.ml/demo/img_run -O /usr/local/bin/img_run
chmod +x /usr/local/bin/img_run
```

# Running images

Images are run by user `qdemo`.

``` sh
screen -S
img_run pibox-kiwix_2018-05-04.img
img_run https://kiwix.ml/images/pibox-kiwix_2018-05-04.img.zip
```

Now host can talk to guest:

``` sh
# ICMP works with tap but not default qemu interface
ping -c 1 192.168.1.3
# SSH is available through both interfaces
ssh pi@192.168.1.3
ssh pi@localhost -p 5022
# full network is exposed to host
curl http://192.168.1.3/
curl -L http://demo.kiwix.ml/
# shutdown the VM
ssh pi@demo "sudo shutdown -P 0"
```

Test the VM from outside: http://demo.kiwix.ml

# Useful commands

If thing go wrong or you want to tweak the config

``` sh
# display nodes in bridge
bridge link

# disable iface
ip link set tap0 down

# remove an iface (tap0) from the bridge
ip link set tap0 nomaster

# delete the bridge
ip link delete br0 type bridge
```

# Scripts & files

## nginx virtual-host

https://kiwix.ml/demo/nginx-vhost

``` conf
server {
	listen 80;
	server_name demo.kiwix.ml kiwix.demo.kiwix.ml sites.demo.kiwix.ml khanacademy.demo.kiwix.ml aflatoun.demo.kiwix.ml edupi.demo.kiwix.ml wikifundi.demo.kiwix.ml;
	root /var/www;
	autoindex on;

	location / {
        proxy_pass http://192.168.1.3;
        proxy_set_header    Host            $host;
        proxy_set_header    X-Real-IP       $remote_addr;
        proxy_set_header    X-Forwarded-for $remote_addr;
        port_in_redirect off;
        proxy_connect_timeout 300;
    }
}
```

## host setup (@reboot)

https://kiwix.ml/demo/host-setup.sh

``` sh
#!/bin/sh

echo "create a TUN interface for Qemu"
tunctl -u qdemo

echo "create a bridge interface"
ip link add br0 type bridge

echo "set up forwarding so image can access internet"
echo 1 > /proc/sys/net/ipv4/conf/tap0/proxy_arp
echo 1 > /proc/sys/net/ipv4/ip_forward
echo 1 > /proc/sys/net/ipv6/conf/all/forwarding
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
iptables -A FORWARD -i br0 -o eth0 -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i eth0 -o br0 -j ACCEPT

echo "remove IP on both ifaces (should not be any)"
ip addr flush dev br0
ip addr flush dev tap0

echo "add TUN interface to the bridge"
ip link set tap0 master br0

echo "bring both up"
ip link set dev br0 up
ip link set dev tap0 up

echo "assign an IP to the bridge. it's our host local IP now"
ifconfig br0 192.168.1.1 netmask 255.255.255.0
```

## guest setup (first-boot)

https://kiwix.ml/demo/guest-setup.sh

``` sh
#!/bin/sh

echo "add IP and iptables conf to rc.local"
sudo bash -c 'orig=$(cat /etc/rc.local | sed -e "$ d") && echo -e "${orig}\n\nifconfig eth0 192.168.1.3 up\nroute add default gw 192.168.1.1\nsleep 20\niptables -t nat -I CAPTIVE_PASSLIST 1 -s 192.168.1.1 -j ACCEPT\nexit 0" > /etc/rc.local && chmod +x /etc/rc.local'

echo "remove cron task clearing-up accepted IP list"
sudo sh -c 'crontab -u root -l |grep -v clean_iptables.sh |crontab -u root -'

echo "execute rc.local"
sudo /etc/rc.local

echo "rename image for demo"
cd /var/lib/ansible/local && sudo /usr/local/bin/ansible-playbook --inventory hosts --tags rename  --extra-vars "tld=kiwix.ml project_name=demo" main.yml
```

Apply it with (enter `raspberry` password at SSH prompt):

``` sh
ssh pi@locahost -p 5022 "sudo ifconfig eth0 192.168.1.3 up && sudo route add default gw 192.168.1.1 && wget https://kiwix.ml/demo/guest-setup.sh -O /tmp/guest-setup.sh && sudo sh /tmp/guest-setup.sh"
```

## `img_run`

https://kiwix.ml/demo/img_run

``` sh
#!/bin/bash
# img_run: launchs a pibox image in qemu using vexpress kernel and tap iface

img=$1

if [ -z "${img}" ] ; then
	echo "Usage: $0 IMG_PATH"
	exit 0
fi

is_url=$(echo "${img}" | grep "^http")
if [ ! -z "${is_url}" ] ; then
	echo "image appears to be an URL, downloading"
	ufname=$(basename "${img}")
	wget -O ~/${ufname} ${img}
	img=${ufname}
fi

is_zip=$(echo "${img}" | grep "zip$")
if [ ! -z "${is_zip}" ] ; then
	echo "image appears to be zipped, extracting"
	zfname=$(basename "${img}")
	unzip -d ~/ ${img}
	img=~/$(echo "${zfname}" | sed "s/.zip//")
fi

if [ ! -f "${img}" ] ; then
	echo "Unable to read image file at ${img}"
	exit 1
fi

if [ ! -f zImage ] ; then
	echo "kernel files not present, downloading"
	wget -O ~/boot.zip http://download.kiwix.org/dev/pibox-installer-vexpress-boot.zip
	unzip boot.zip
	mv ~/pibox-installer-vexpress-boot/* ~/.
	rmdir ~/pibox-installer-vexpress-boot
fi

# max ram to use by QEMU guest (format: XM or XG)
if [ -z "${QEMU_RAM}" ] ; then
	QEMU_RAM="2040M"
fi

# adjust accelearation based on number of cores
nb_cores=$(nproc)
if [ ${nb_cores} -ge 3 ] ; then
    SMP_OPT="-smp $(expr ${nb_cores} - 1) --accel tcg,thread=multi"
else
    SMP_OPT=""
fi

echo "hooray. starting ${img}"

qemu-system-arm \
    -m ${QEMU_RAM} \
    -M vexpress-a15 \
    -kernel ~/zImage \
    -dtb ~/vexpress-v2p-ca15_a7.dtb \
    -append "root=/dev/mmcblk0p2 console=ttyAMA0 console=tty" \
    -serial stdio \
    -drive "format=raw,if=sd,file=${img}" \
    -display none \
    ${SMP_OPT} \
    -netdev user,id=eth1,hostfwd=tcp::5022-:22 \
    -device virtio-net-device,netdev=eth1 \
    -netdev tap,id=eth0,ifname=tap0,script=no,downscript=no \
    -device virtio-net-device,netdev=eth0

```
