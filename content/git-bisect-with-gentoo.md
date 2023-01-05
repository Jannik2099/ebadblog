Title: Git Bisect with Gentoo and Systemd
Date: 2023-01-05
Category: Gentoo
Tags: Development, Gentoo
Summary: Gentoo and Systemd make for a wonderful bisect workflow. Let's have a look!

# Git Bisect

To begin with, let's quickly recap what `git bisect` does.

A common scenario in software is that a new version introduces regressions or bugs in some components. Bisect allows you to... bisect the commit range between the previous, good version and the new, bad version. Bisect utilizes binary search and thus has a complexity of just `O(log(N))` for `N` commits. This means Bisect can be used for projects of any scale, and in fact it is regularly used in big projects such as the linux kernel.

While the binary search reduces the effort involved quite a lot, having to rebuild, retest etc. a program a dozen times is still incredibly tedious. For this, git offers `git bisect run`. Bisect run allows you to automate this procedure with a simple bash script that returns bad / good / skip for any given commit.

The `git-bisect` man page has more details.

# Bisecting complex and interlinked software

While a simple Bisect run script is enough to find bugs for simple programs such as CLI utilities, it can easily get more complicated with bigger programs. For example, a given program may depend on specific library versions, may not expose a stable ABI itself and thus necessate rebuilds in other programs, or may have even more exotic demands for the environment (think about bisecting a kernel!). Thus, in many cases it can be desirable to have the commit that is being bisected integrated with the system much like a distro package is.

## Portage, your favourite package manager!

Disclaimer: explaining how to use portage is WAY out of scope for this article. This is not meant as a "if you want to debug, use portage", but rather as a "if you are already using portage and want to debug, do this!"

While most distro package managers allow users to quickly create custom packages, few are able to transparently handle the issues mentioned above. Thankfully, portage is!

I do not want to go into details here because frankly portage is an enigma of generations-spanning python hellcode that I do not dare to decipher, but the gist is that portage supports concepts like reverse dependency tracking, overriding of system and other custom packages, and even building directly from specific git commits!

While portage gives us a lot of power, we probably do not want to unleash untested git commits onto our system. Which brings us to the next step:

## systemd-nspawn, your simple chroot-container mix!

Let me prephrase that systemd-nspawn specifically is absolutely not a hard requirement here, other container tools like lxc or podman work just as well, even bare chroots would probably do the job most of the time. I just found nspawn to be the most comfortable for this workflow for various reasons.

Nspawn is a container tool similar to Docker, but with a few differences. Nspawn supports so called "OS containers", which are containers that run their own init (usually systemd). Anyone who tried to do the same in Docker knows what a vast difference to application containers this is. However, nspawn can also be used to run traditional application containers.

Nspawn also works directly with a root directory, unlike e.g. Docker where the root image is in `/var/lib/onlygodknows`, and you need a myriad of commands to extract, manipulate and repackage an image. This makes it much better suited for the "modify and test" workflow that is Bisect.

# Putting it all together

Let's take ffmpeg as an example. We need:

## The nspawn container

We'll take a [Gentoo systemd stage3](https://www.gentoo.org/downloads/) and extract it into `gentoo`
```
wget https://bouncer.gentoo.org/fetch/root/all/releases/amd64/autobuilds/20230101T164658Z/stage3-amd64-systemd-20230101T164658Z.tar.xz # Latest as of time of writing
mkdir gentoo
tar xvf stage3-amd64-systemd-20230101T164658Z.tar.xz -C gentoo
```

At this point we are already good to go to use most of nspawns features. Let's hop in!

```
systemd-nspawn -D gentoo --pipe bash << 'EOF'
emerge-webrsync
emerge your-favourite-editor your-favourite-utilities
echo "EGIT_CLONE_TYPE=mirror" >> /etc/portage/make.conf

# Remember to set use flags, compiler flags / sanitizers as desired for the package
echo "media-video/ffmpeg **" >> /etc/portage/package.accept_keywords/bisect

# This is so that systemd-nspawn --boot gets a shell without interaction
mkdir -p /etc/systemd/system/console-getty.service.d/
echo "
[Service]
ExecStart=
ExecStart=-/sbin/agetty -o '-p -f -- \\\\u' --noclear --keep-baud --autologin root - 115200,38400,9600 \$TERM" > /etc/systemd/system/console-getty.service.d/autologin.conf

EOF
```

## The git repo

```
git clone https://git.ffmpeg.org/ffmpeg.git
# These tags are just examples!
git bisect start
git bisect good n4.2.7
git bisect bad n4.2.8
```

## The bisect-run script

```
#!/usr/bin/env bash

COMMIT=$(git rev-base --short HEAD)

echo "building ffmpeg"
systemd-nspawn -D ../gentoo -E EGIT_COMMIT=$COMMIT emerge media-video/ffmpeg  &>/dev/null || exit 125
echo "testing ffmpeg"
systemd-nspawn -D ../gentoo ffmpeg *whatever input caused your crash* &>/dev/null || exit 1

# If using e.g ASAN, you may want something like
#echo "building ffmpeg"
#systemd-nspawn -D ../gentoo -E EGIT_COMMIT=$COMMIT -E ASAN_OPTIONS="verify_asan_link_order=0:detect_leaks=0" emerge media-video/ffmpeg &>/dev/null || exit 125
#echo "testing ffmpeg"
#systemd-nspawn -D ../gentoo -E ASAN_OPTIONS="log_path=/log-$COMMIT.txt" ffmpeg *whatever input caused your crash* &>/dev/null || exit 1
# instead
# The ASAN_OPTIONS are usually required for portage's sandbox

exit 0
```

Notice the `|| exit 125` after the build step - Bisect run recognizes this exit code as "skip", this is useful when e.g. the given commit fails to build.

If you are trying to find a regression in critical packages where a bad build may render the container unusable, you should copy it beforehand or work with nspawns `-x` option.

And that's pretty much it! Now all that's left to do is

```
chmod +x bisect.sh
git bisect run ./bisect.sh
```

Of course there can be many more specifc tweaks depending on the program in question, and there's also room for optimization such as caching or sharing the gentoo repo (or even bisecting the gentoo repo itself!) - coming up with these extensions is left as an excercise for the reader.

# Bonus case: debugging systemd

I recently had to debug systemd itself this way. The procedure is very similar, except that we need to use `--boot` to get nspawn to run systemd. There are a few additions and alterations to account for the extra requirements. Needless to say, do not blindly copy this into your command prompt.

Preparing the container:

```
# Insert "install Gentoo" meme
wget https://bouncer.gentoo.org/fetch/root/all/releases/amd64/autobuilds/20230101T164658Z/stage3-amd64-systemd-20230101T164658Z.tar.xz # Latest as of time of writing
mkdir gentoo
tar xvf stage3-amd64-systemd-20230101T164658Z.tar.xz -C gentoo

systemd-nspawn -D gentoo --pipe bash << 'EOF'
emerge-webrsync
echo "EGIT_CLONE_TYPE=mirror" >> /etc/portage/make.conf

echo "sys-apps/systemd **" >> /etc/portage/package.accept_keywords/bisect
mkdir -p /etc/portage/env
# nested heredoc is cursed
cat << 'ASAN' > /etc/portage/env/asan
ASAN_OPTIONS="verify_asan_link_order=0"
MYMESONARGS="-Db_sanitize=address"
CFLAGS="${CFLAGS} -g3"
CXXFLAGS="${CXXFLAGS} -g3"
FEATURES="${FEATURES} nostrip"
ASAN
echo "sys-apps/systemd asan" >> /etc/portage/package.env


mkdir -p /etc/systemd/system/console-getty.service.d/
echo "
[Service]
ExecStart=
ExecStart=-/sbin/agetty -o '-p -f -- \\\\u' --noclear --keep-baud --autologin root - 115200,38400,9600 \$TERM" > /etc/systemd/system/console-getty.service.d/autologin.conf

# This was required because some services linked against libsystemd start with a fresh env
echo DefaultEnvironment=ASAN_OPTIONS=\"verify_asan_link_order=0\" > /etc/systemd/system.conf

# This causes --boot to shutdown immediately (with exit code 0) if systemd manages to start
echo "shutdown now" > /root/.bash_profile

EOF
```

Preparing the repository:

```
git clone https://github.com/systemd/systemd.git
cd systemd

cat << 'EOF' > bisect.sh
#!/usr/bin/env bash
COMMIT=$(git rev-parse --short HEAD)

systemd-nspawn -D ../gentoo -E ASAN_OPTIONS="verify_asan_link_order=0:detect_leaks=0" -E EGIT_OVERRIDE_COMMIT_SYSTEMD_SYSTEMD=$COMMIT -E EGIT_CLONE_TYPE=mirror emerge sys-apps/systemd &>/dev/null || exit 125

systemd-nspawn -D ../gentoo -E ASAN_OPTIONS="verify_asan_link_order=0:detect_leaks=0:log_path=/log-$COMMIT.txt" --boot &>/dev/null || exit 1

exit 0
EOF

chmod +x bisect.sh
```

And victory at last:

```
git bisect start
git bisect good v251
git bisect bad v252
git bisect run ./bisect.sh
```

Needless to say, this didn't end up helping me because the bug was somewhere else. Fun!