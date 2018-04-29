#!/bin/bash
#
# creates a kiwix base image file off a raspbian one
# see README.md for details

####### PARAMETERS

# size of target image in GB
if [ -z "${SD_SIZE_GB}" ] ; then
	SD_SIZE_GB=4
fi

# size of / partition wihin target image (in GB). min. 2GB
if [ -z "${SYSPART_SIZE_GB}" ] ; then
	SYSPART_SIZE_GB=3
fi

# max ram to use by QEMU guest (format: XM or XG)
if [ -z "${QEMU_RAM}" ] ; then
	QEMU_RAM="2000M"
fi

if [ ! -z "${HAS_LOOP}" ] ; then
	HAS_LOOP=1
else
	HAS_LOOP=0
fi

########

function dirof {
	echo "$( cd "$(dirname "$1")" ; pwd -P )"
}
ROOT=$(dirof $0)

ANSIBLECUBE_VERSION=0.5  # ansiblecube version/branch to use
RASPBIAN_VERSION="2017-07-05/2017-07-05-raspbian-jessie-lite"
# RASPBIAN_VERSION="2018-03-14/2018-03-13-raspbian-stretch-lite"
QEMU_DL_VERSION="2.11.1"

# URLS
RASPBIAN_URL="http://downloads.raspberrypi.org/raspbian_lite/images/raspbian_lite-${RASPBIAN_VERSION}.zip"
VEXPRESS_URL="http://download.kiwix.org/dev/pibox-installer-vexpress-boot.zip"
QEMU_URL=http://download.qemu-project.org/qemu-${QEMU_DL_VERSION}.tar.xz
ANSIBLECUBE_URL=https://framagit.org/ideascube/ansiblecube/repository/oneUpdateFile${ANSIBLECUBE_VERSION}/archive.zip

# temp vars
QEMU_BINARY="qemu-system-arm"
QEMU_PATH=""  # populated later-on

VIRTUAL_ENV=$ROOT/pibox-img-creator_env

raspbian_zip=$ROOT/`basename ${RASPBIAN_URL}`
raspbian_img=`echo ${raspbian_zip} | sed 's/\.zip$/.img/'`

vexpress_zip=$ROOT/`basename ${VEXPRESS_URL}`
vexpress_dir=`echo ${vexpress_zip} | sed 's/\.zip//'`

ansible_zip=$ROOT/oneUpdateFile${ANSIBLECUBE_VERSION}.zip

build_img=$ROOT/pibox-kiwix-`date +"%Y-%m-%d"`-BUILDING.img
final_img=`echo ${build_img} | sed 's/\-BUILDING//'`
zip_file=${final_img}.zip

data_part_size=`python -c "print(${SD_SIZE_GB} - ${SYSPART_SIZE_GB})"`

function usage {
	echo "Usage: $0 [help|setup|clean|run]"
	exit
}

function fail {
	if [ ! -z "${loopdev}" ] ; then
		sudo losetup -d ${loopdev}
	fi
	echo "ERROR: $1"
	exit 1
}

function img_info {
	$QEMU_PATH/qemu-img info -f raw $1
}

function img_resize {
	img=$1
	size=$2
	sizeb=`python -c "print(${size}*2**30)"`
	
	img_info $img

	echo "Resizing ${img} to ${sizeGB} (${sizeb} b)"

	$QEMU_PATH/qemu-img resize -f raw ${img} ${sizeb}

	img_info ${img}
}

function run {
	# ensure setup ran successfuly
	setup

	if [ -z "${QEMU_PATH}" ] ; then
		fail "setup failed."
	fi

	if [ ${SD_SIZE_GB} -lt ${SYSPART_SIZE_GB} ] ; then
		fail "SD size (${SD_SIZE_GB}GB) is less than system size (${SYSPART_SIZE_GB}GB)"
	fi

	if [ ${SYSPART_SIZE_GB} -le 2 ] ; then
		fail "System partition needs more than 2GB"
	fi

	echo "starting with SD_SIZE_GB=${SD_SIZE_GB} and SYSPART_SIZE_GB=${SYSPART_SIZE_GB}"

	echo "Downloading Qemu dependencies (vexpress)"
	wget -O ${vexpress_zip} -c ${VEXPRESS_URL}
	if [ ! -d ${vexpress_dir} ] ; then
		unzip ${vexpress_zip}
	fi

	echo "Downloading raspbian image"
	wget -O ${raspbian_zip} -c ${RASPBIAN_URL}
	if [ ! -f $raspbian_img ] ; then
		unzip ${raspbian_zip}
	fi

	echo "Downloading latest ansiblecube (${ANSIBLECUBE_VERSION})"
	wget -O ${ansible_zip} -c ${ANSIBLECUBE_URL}
	if [ ! -d $ROOT/ansiblecube ] ; then
		unzip ${ansible_zip}
		mv $ROOT/ansiblecube-oneUpdateFile${ANSIBLECUBE_VERSION}* $ROOT/ansiblecube
	fi

	echo "Copying raspbian image to $build_img"
	cp $raspbian_img $build_img

	echo "Preparing partitions for the new image"

	echo "  -- displaying current (default) size & partition table"
	img_info $build_img || fail "Unable to read image size info"
	fdisk -l $build_img || fail "Unable to read image partition table"

	echo "  -- resizing image to $SD_SIZE_GB GB"
	img_resize $build_img $SD_SIZE_GB || fail "Unable to resize image file"

	# we want fdisk's output without whole path so it's cleaner to parse
	cd $(dirof ${build_img})
	local build_img_fname=`basename ${build_img}`
	local fdisk_output=`fdisk -l ${build_img_fname}`
	local fdisk_worked=$?
	cd -
	if [ ${fdisk_worked} -ne 0 ] ; then
		fail "Unable to read image partition table"
	else
		echo "${fdisk_output}"
	fi
	local boundaries_str=`echo "${fdisk_output}" | python $ROOT/partition_boundaries.py ${SYSPART_SIZE_GB} ${SD_SIZE_GB}`
	if [ $? -ne 0 ] ; then
		fail "Failed to get information from partition table of image."
	else
		echo "Boundaries: ${boundaries_str}"
	fi
	local boundaries=(${boundaries_str// / })
	
	echo " -- resizing / partition to match ${SYSPART_SIZE_GB}GB"
	sudo LANG=C fdisk $build_img <<END_OF_CMD
d
2
n
p
2
${boundaries[0]}
${boundaries[1]}
w
END_OF_CMD
	
	if [[ $? -ne 0 ]] ; then
		fail "Unable to resize partition /"
	fi

	echo "  -- creating a third partition"
	sudo LANG=C fdisk $build_img <<END_OF_CMD
n
p
3
${boundaries[2]}
${boundaries[3]}
t
3
7
w
END_OF_CMD

	if [[ $? -ne 0 ]] ; then
		fail "Unable to create third partition"
	fi

	if [ ${HAS_LOOP} -eq 1 ] ; then
		echo "  -- preparing loop device for image"
		loopdev=`sudo losetup --partscan --show --find $build_img`
		if [ $? -ne 0 -o -z "${loopdev}" ] ; then
			fail "Unable to get loop device"
		else
			echo "   loop device is ${loopdev}"
		fi

		echo "  - resizing filesystem for / partition"
		sudo e2fsck -p -f ${loopdev}p2 || fail "Unable to fsck / partition"
		sudo resize2fs ${loopdev}p2 || fail "Unable to resize filesystem for /"

		echo "  -- formatting 3rd partition in exfat"
		sudo mkfs.exfat ${loopdev}p3 || fail "Unable to create exfat filesystem for third partition"
		
		echo "  -- releasing loop device for image"
		sudo losetup -d ${loopdev} || fail "Unable to release loop device"

		local extra_opts=""
	else
		local extra_opts=" resize"
	fi

	echo "Setting-up python tools"
	if [ ! -d $VIRTUAL_ENV ] ; then
		virtualenv $VIRTUAL_ENV || fail "Unable to create virtualenv"
	fi
	wget -O ${ROOT}/get-pip.py -c https://bootstrap.pypa.io/get-pip.py
	$VIRTUAL_ENV/bin/python ${ROOT}/get-pip.py
	$VIRTUAL_ENV/bin/pip install paramiko
	$VIRTUAL_ENV/bin/python $ROOT/create_pibox_master.py "$build_img" "${QEMU_PATH}" "${QEMU_RAM}"${extra_opts}

	if [ $? -eq 0 -a -f $build_img ] ; then
		zip -9 ${zip_file} ${final_img}
		ls -lh $zip_file
	fi
}

function clean {
	rm -rf $ROOT/$vexpress_dir
	rm -f $ROOT/$vexpress_zip
	rm -f $ROOT/$raspbian_img
	rm -f $ROOT/$raspbian_zip
	rm -f $ROOT/$build_img
	rm -f $ROOT/$zip_file
	rm -rf $ROOT/ansiblecube
	rm -rf $ROOT/qemu-${QEMU_DL_VERSION}
}

function compile_qemu {
	# download and compile recent QEMU
	# copies qemu-system-arm and qemu-img to $ROOT
	local qemu_archive=$ROOT/`basename ${QEMU_URL}`
	wget -O ${qemu_archive} -c $QEMU_URL && 
		tar -xf ${qemu_archive} -C ${ROOT} &&
		# rm ${qemu_archive} &&
		cd $ROOT/qemu-${QEMU_DL_VERSION} && ./configure \
		    --target-list=arm-softmmu \
		    --static \
		    --disable-gtk \
		    --disable-cocoa \
		    --disable-libusb \
		    --disable-glusterfs \
		    --disable-smartcard \
		    --disable-usb-redir \
		    --python=python2 &&
		make &&
		mv -v arm-softmmu/qemu-system-arm $ROOT/ && mv -v qemu-img $ROOT/ && cd - && return 0

	return 1
}

function qemu_version_ok {
	# whether a version string is an acceptable qemu version for us
	# we want 2.8+
	local qemu_version=$1
	local qemu_major=`echo $qemu_version | awk 'BEGIN {FS="."} {print($1)}'`
	local qemu_minor=`echo $qemu_version | awk 'BEGIN {FS="."} {print($2)}'`
	if [ $qemu_major -lt 2 ] ; then
		echo "nok"
	fi

	if [ $qemu_major -eq 2 -a $qemu_minor -lt 8 ] ; then
		echo "nok"
	fi
	echo "ok"
}

function get_qemu_version {
	# the QEMU version of a qemu binary
	local version=`$1 --version | head -n 1 | awk '{print($4)}'`
	echo "${version}"
}

function find_qemu {
	# search for qemu-bin in local folder and system path
	# then check its version and return the first that's correct
	echo "looking for QEMU..."
	local qemu_bins=`find $ROOT -name $QEMU_BINARY | awk 'NF'`
	local sys_qemu=`command -v $QEMU_BINARY | awk 'NF'`
	if [ $? -eq 0 ] ; then
		qemu_bins="${qemu_bins}${sys_qemu}"
	fi

	if [ `echo $qemu_bins | awk 'NF' | wc -l` -gt 0 ] ; then
		for qemu_bin in "${qemu_bins[@]}"
		do
			local qbv=$(get_qemu_version ${qemu_bin})
			echo -n ".. found ${qemu_bin} (v${qbv}) ... "
			local qbvok=$(qemu_version_ok ${qbv})
			if [ "${qbvok}a" = "oka" ] ; then
				echo "OK"
				QEMU_PATH=$(dirof $qemu_bin)
				return 0
			else
				echo "NOT OK"
			fi
		done
	else
		echo ".. not found."
	fi
	return 1
}

function setup {
	# checks that required tools are present
	echo "looking for base dependencies..."
	if [ ${HAS_LOOP} -eq 1 ] ; then
		declare -a local deps=("wget" "unzip" "python" "virtualenv" "fdisk" "e2fsck" "resize2fs" "losetup" "mkfs.exfat")
	else
		declare -a local deps=("wget" "unzip" "python" "virtualenv" "fdisk")
	fi
	local missing_dep=0
	for dep in "${deps[@]}"
	do
		dep_path=`command -v ${dep}`
			if [ $? -ne 0 ] ; then
				echo ".. missing ${dep}"
				missing_dep=1
			else
				echo ".. ${dep_path}"
			fi
	done
	if [ $missing_dep -eq 1 ] ; then
		fail "You are missing some base package(s) for this tool. Please install them first."
	fi

	# find best match for qemu
	find_qemu

	if [ -z "${QEMU_PATH}" ] ; then
		echo "could not find a compatible QEMU version. compiling..."

		sleep 2
		compile_qemu

		if [ $? -eq 0 ] ; then
			echo "compilation successful. please relaunch this script to check."
			return 0
		else
			echo "compilation failed. please check output and retry. Missing build tools?"
			return 1
		fi
	else
		echo ". using ${QEMU_PATH}/${QEMU_BINARY}"
		return 0
	fi
}

if [ "$1a" = "runa" ]; then
	if [ ! -z "${2}" ] ; then
		SD_SIZE_GB=$2
	fi
	run
elif [ "$1a" = "cleana" ]; then
	clean
elif [ "$1a" = "setupa" ]; then
	setup
else
	usage
fi
