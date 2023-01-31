Title: Git Bisect part 2, now with Qemu and Kernels!
Date: 2023-01-31
Category: Gentoo
Tags: Development, Gentoo
Summary: In this continuation we expand the previous concepts to bisecting a kernel with Qemu.

# A recap

In the [previous article](/git-bisect-with-gentoo-and-systemd.html) we explored automating a bisect of an userspace program via containers. When you want to bisect something that cannot just run in a namespace, such as a kernel itself, things get slightly more complicated. This time, we will use Qemu and Libvirt to automate a tiny VM that loads our kernel, runs the regression test and returns the result.

## The VM image

We again start with a systemd-nspawn container. Assuming that our container filesystem resides in `/var/lib/libvirt/images/gentest` and the cloned linux source tree in the `/linux` directory therein, we end up with the following script to build and install the kernel:

```
#!/usr/bin/env bash

systemd-nspawn -D /var/lib/libvirt/images/gentest --pipe bash << 'EOF'
set -e
cd /linux
rm -rf /lib/modules/
export KVER=$(git rev-parse --short HEAD)
make olddefconfig
sed -i "s/CONFIG_LOCALVERSION=.*/CONFIG_LOCALVERSION=\"-$KVER\"/" .config
make -j$(nproc)'
make modules_install
dracut --force --kver "$(make kernelrelease)" --kernel-image $(realpath arch/x86/boot/bzImage) initramfs
EOF
[ $? == 0 ] || exit 125 # git bisect skip, see previous article
```

This will give us the following:

- a kernel image in `/var/lib/libvirt/images/gentest/linux/arch/x86/boot/bzImage`
- an initramfs in `/var/lib/libvirt/images/gentest/linux/initramfs`
- the kernel modules installed in `/var/lib/libvirt/images/gentest/lib/modules/`
- the commit hash added to the LOCALVERSION (used by module lookup and uname -r)

We will use Qemu's direct kernel boot feature later on, if your ISA / VM setup does not support this then you will have to set up a rudimentary bootloader such as systemd-boot in the container aswell.

It is generally recommended to trim the kernel config as much as possible to speed up the rebuilds. All we need for this setup is the various VIRTIO configs, and the usual knobs such as cgroups, devtmpfs and various socket types to host a normal userspace environment. And of course the config for the subsystem that you want to bisect.

### The VM image is not an image

The acute observer will have noticed that our file in `/var/lib/libvirt/images/` is, in fact, not a Qemu image in a `.raw` or `.qcow2` format, but a directory structure that resembles a root filesystem.

Indeed we won't use traditional emulated block devices, but `virtiofs`. This has two reasons:

- it's faster, I think
- we can directly interact and manipulate the image, even when the VM is running

This means that we don't have to "repackage" (mount loopback file, change / copy files, unmount, etc.) a new image file for each bisect iteration, but can instead operate inside the image directory directly. It also allows us to exchange arbitrary files between the VM and Host without the need for NFS, ssh or other file sharing methods. This can be useful when you need to extract bigger files like coredumps.

Note: it would be cleaner to expose the filesystem as read-only to the VM to avoid potential corruption due to broken commits and for better reproducibility, but I couldn't be bothered at the time. The extra setup for this is minimal, a tmpfs-backed overlayfs for / would suffice.

## The VM configuration

We need to set up just a few things:

- direct kernel boot
- the `virtiofs` share (and a required memfd memory backing)
- the `qemu-guest-agent` socket

We'll also add some extras for comfort:

- A virtio rng device
- A virtio video device
- A virtio keyboard input device
- A spice display
- A spicevmc socket

There are also some devices that libvirt sets up anyways, such as the PCIe and USB controller.

We end up with the following libvirt xml:

<details>
    <summary>XML</summary>

```
<domain type="kvm">
  <name>gentest</name>
  <uuid>df146158-d71e-4adb-8850-a758ae523f7c</uuid>
  <metadata>
    <libosinfo:libosinfo xmlns:libosinfo="http://libosinfo.org/xmlns/libvirt/domain/1.0">
      <libosinfo:os id="http://gentoo.org/gentoo/rolling"/>
    </libosinfo:libosinfo>
  </metadata>
  <memory unit="KiB">1048576</memory>
  <currentMemory unit="KiB">1048576</currentMemory>
  <memoryBacking>
    <source type="memfd"/>
    <access mode="shared"/>
  </memoryBacking>
  <vcpu placement="static">4</vcpu>
  <os>
    <type arch="x86_64" machine="pc-q35-7.2">hvm</type>
    <kernel>/var/lib/libvirt/images/gentest/linux/arch/x86/boot/bzImage</kernel>
    <initrd>/var/lib/libvirt/images/gentest/linux/initramfs</initrd>
    <cmdline>rootfstype=virtiofs root=root rw</cmdline>
    <boot dev="hd"/>
  </os>
  <features>
    <acpi/>
    <apic/>
    <vmport state="off"/>
  </features>
  <cpu mode="host-passthrough" check="none" migratable="on"/>
  <clock offset="utc">
    <timer name="rtc" tickpolicy="catchup"/>
    <timer name="pit" tickpolicy="delay"/>
    <timer name="hpet" present="no"/>
  </clock>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>destroy</on_crash>
  <pm>
    <suspend-to-mem enabled="no"/>
    <suspend-to-disk enabled="no"/>
  </pm>
  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>
    <controller type="usb" index="0" model="qemu-xhci" ports="15">
      <address type="pci" domain="0x0000" bus="0x02" slot="0x00" function="0x0"/>
    </controller>
    <controller type="pci" index="0" model="pcie-root"/>
    <controller type="pci" index="1" model="pcie-root-port">
      <model name="pcie-root-port"/>
      <target chassis="1" port="0x10"/>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x02" function="0x0" multifunction="on"/>
    </controller>
    <controller type="pci" index="2" model="pcie-root-port">
      <model name="pcie-root-port"/>
      <target chassis="2" port="0x11"/>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x02" function="0x1"/>
    </controller>
    <controller type="pci" index="3" model="pcie-root-port">
      <model name="pcie-root-port"/>
      <target chassis="3" port="0x12"/>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x02" function="0x2"/>
    </controller>
    <controller type="pci" index="4" model="pcie-root-port">
      <model name="pcie-root-port"/>
      <target chassis="4" port="0x13"/>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x02" function="0x3"/>
    </controller>
    <controller type="pci" index="5" model="pcie-root-port">
      <model name="pcie-root-port"/>
      <target chassis="5" port="0x14"/>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x02" function="0x4"/>
    </controller>
    <controller type="pci" index="6" model="pcie-root-port">
      <model name="pcie-root-port"/>
      <target chassis="6" port="0x15"/>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x02" function="0x5"/>
    </controller>
    <controller type="pci" index="7" model="pcie-root-port">
      <model name="pcie-root-port"/>
      <target chassis="7" port="0x16"/>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x02" function="0x6"/>
    </controller>
    <controller type="pci" index="8" model="pcie-root-port">
      <model name="pcie-root-port"/>
      <target chassis="8" port="0x17"/>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x02" function="0x7"/>
    </controller>
    <controller type="pci" index="9" model="pcie-root-port">
      <model name="pcie-root-port"/>
      <target chassis="9" port="0x18"/>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x03" function="0x0" multifunction="on"/>
    </controller>
    <controller type="pci" index="10" model="pcie-root-port">
      <model name="pcie-root-port"/>
      <target chassis="10" port="0x19"/>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x03" function="0x1"/>
    </controller>
    <controller type="pci" index="11" model="pcie-root-port">
      <model name="pcie-root-port"/>
      <target chassis="11" port="0x1a"/>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x03" function="0x2"/>
    </controller>
    <controller type="pci" index="12" model="pcie-root-port">
      <model name="pcie-root-port"/>
      <target chassis="12" port="0x1b"/>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x03" function="0x3"/>
    </controller>
    <controller type="pci" index="13" model="pcie-root-port">
      <model name="pcie-root-port"/>
      <target chassis="13" port="0x1c"/>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x03" function="0x4"/>
    </controller>
    <controller type="pci" index="14" model="pcie-root-port">
      <model name="pcie-root-port"/>
      <target chassis="14" port="0x1d"/>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x03" function="0x5"/>
    </controller>
    <controller type="virtio-serial" index="0">
      <address type="pci" domain="0x0000" bus="0x03" slot="0x00" function="0x0"/>
    </controller>
    <controller type="sata" index="0">
      <address type="pci" domain="0x0000" bus="0x00" slot="0x1f" function="0x2"/>
    </controller>
    <filesystem type="mount" accessmode="passthrough">
      <driver type="virtiofs"/>
      <source dir="/var/lib/libvirt/images/gentest"/>
      <target dir="root"/>
      <address type="pci" domain="0x0000" bus="0x01" slot="0x00" function="0x0"/>
    </filesystem>
    <channel type="unix">
      <target type="virtio" name="org.qemu.guest_agent.0"/>
      <address type="virtio-serial" controller="0" bus="0" port="1"/>
    </channel>
    <channel type="spicevmc">
      <target type="virtio" name="com.redhat.spice.0"/>
      <address type="virtio-serial" controller="0" bus="0" port="2"/>
    </channel>
    <input type="keyboard" bus="virtio">
      <address type="pci" domain="0x0000" bus="0x06" slot="0x00" function="0x0"/>
    </input>
    <input type="mouse" bus="ps2"/>
    <input type="keyboard" bus="ps2"/>
    <graphics type="spice" autoport="yes">
      <listen type="address"/>
      <image compression="off"/>
    </graphics>
    <audio id="1" type="spice"/>
    <video>
      <model type="virtio" heads="1" primary="yes"/>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x01" function="0x0"/>
    </video>
    <memballoon model="virtio">
      <address type="pci" domain="0x0000" bus="0x04" slot="0x00" function="0x0"/>
    </memballoon>
    <rng model="virtio">
      <backend model="random">/dev/urandom</backend>
      <address type="pci" domain="0x0000" bus="0x05" slot="0x00" function="0x0"/>
    </rng>
  </devices>
</domain>
```

</details>

Note the parameters for direct kernel boot in the `<os>` section.

## Interacting with the VM

We now have a libvirt domain that we can start and stop, but we still need a way to (programatically) interact with it. Enter `qemu-guest-agent`!

`qemu-guest-agent` is an... agent that runs in the guest and is... part of the Qemu project. In more helpful terms, `qemu-guest-agent` is an RPC endpoint in the guest that allows the host to query information and send commands. The protocol uses the JSON format and is [documented here](https://qemu.readthedocs.io/en/latest/interop/qemu-ga-ref.html). A few examples of generally useful commands are:

- `guest-fsfreeze-freeze`
- `guest-ssh-add-authorized-keys`
- `guest-network-get-interfaces`

Today, we will be using `guest-exec` and `guest-exec-status`. Our scenario is that the kernel regression manifests as a backtrace in dmesg immediately upon boot. Thus, we want to boot the VM, run dmesg, capture the output, and grep it for the backtrace we are looking for. We will be using the excellent `jq` program to format and manipulate the JSON strings.

First, we need to start the VM and wait for `qemu-guest-agent` to be ready.

```
DOMAIN=gentest
virsh start $DOMAIN

JSON=$(echo '{
"execute":"guest-ping"
}
' | jq -c '')
while ! virsh qemu-agent-command $DOMAIN $JSON &>/dev/null; do
        sleep 1
done
# Note: you may want to add more robust logic
# to detect a boot timeout and return 125 to git bisect
```

Next, run dmesg and capture the output.

```
JSON=$(echo '{
"execute":"guest-exec",
"arguments":{
"path":"dmesg",
"capture-output":true
}
}
' | jq -c '')
JRET=$(virsh qemu-agent-command $DOMAIN $JSON)
sleep 1
# if your command takes longer to finish,
# you will need a guest-exec-status loop
```

`guest-exec` is an async API: it returns the spawned PID immediately, the status, return code and optionally returned data has to be reaped later on with `guest-exec-status`. We can also shutdown the VM once we collected the output we wanted.

```
PID=$(echo $JRET | jq '.return.pid')
JSON=$(echo '{
"execute":"guest-exec-status",
"arguments":{
"pid":'$PID'
}
}
' | jq -c '')
JRET=$(virsh qemu-agent-command $DOMAIN $JSON)
OUT=$(echo $JRET | jq -r '.return."out-data"' | base64 -d)

virsh shutdown --mode=agent $DOMAIN
```

Finally, grep for the expected backtrace and return the result for `git bisect-run`.

```
# the exact pattern you are looking for might vary
echo $OUT | grep -q -E '\[ cut here \]'
[ $? == 0 ] && exit 1 || exit 0
```

Note that you may want to make some of the `qemu-guest-agent` calls more robust and return 125 if they fail.

# Closing words

Of course this is a rather rudimentary example. However with native file sharing through `virtiofs` and command execution via `qemu-guest-agent`, you should be able to model more complex regression triggers with ease.

The native interaction through `virtiofs` allows for quick manipulation just like in the previous article. Unlike e.g. a loopback mount, `virtiofs` requires no mount / unmount operations on the host side whatsoever.

The execution methods of `qemu-guest-agent` remove the need for configuring networking & ssh in the guest and the associated burdens like "why did the guest get a different IP this time?" - this should also come in handy when the regression you want to bisect is in the network layer.