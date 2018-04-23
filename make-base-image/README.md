pibox-kiwix base image creator
===

pibox-installer 2.0+ uses a custom base image based off raspbian-lite with the following modifications (not exhaustive):

* `2017-07-05-raspbian-jessie-lite` 
* SSH enabled
* 3GB `/` partition (ext4)
* 1GB `/data` partition (extfat)
* [ansiblecube 0.5](https://framagit.org/ideascube/ansiblecube/tree/oneUpdateFile0.5) deployed: `nginx`, `ideascube`, `kiwix-serve`, etc.

## requirements

* Python 2.7+
* Qemu 2.8+ (compiled if not found)
* `apt install python python-virtualenv wget unzip exfat-utils e2fsprogs util-linux mount`
* **sudo powers**: `fdisk`, `losetup`, `e2fsck`, `resize2fs`, `mkfs.exfat`)

Sample: `sudo visudo -f /etc/sudoers.d/pibox-img-creator`

``` ini
User_Alias PICUSER = myusername
PICUSER ALL = (ALL) NOPASSWD: /sbin/fdisk
PICUSER ALL = (ALL) NOPASSWD: /sbin/losetup
PICUSER ALL = (ALL) NOPASSWD: /sbin/e2fsck
PICUSER ALL = (ALL) NOPASSWD: /sbin/resize2fs
PICUSER ALL = (ALL) NOPASSWD: /sbin/mkfs.exfat
```

## setup

To make sure you have all the required dependencies, run the setup script.

It will check that mandatory programs are available and verify the version of Qemu. If Qemu is not present or too old, it will compile a recent one.

``` bash
./make-image.sh setup
```

## building the image

``` bash
./make-image.sh run [SD_SIZE_GB]
```

You can customize the image or the guest resources through variables:

``` bash
SYSPART_SIZE_GB=3 QEMU_RAM="2000M" ./make-image.sh run 8
```
