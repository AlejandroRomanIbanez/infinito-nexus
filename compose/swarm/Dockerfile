# Node image for the swarm DR test cluster. python3 enables the
# ansible-over-docker provisioning before the .deb bootstrap; baking the
# packages removes every per-node runtime apt install that hit act's flaky
# embedded resolver (EAI_AGAIN): dnsmasq (lab DNS), openssh server/client +
# rsync (backup pull chain), cryptsetup + e2fsprogs (LUKS drill device).
# systemd-resolved is masked so it never races dnsmasq for port 53.
FROM jrei/systemd-ubuntu:24.04

RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
        dnsmasq python3 openssh-server openssh-client rsync cryptsetup e2fsprogs && \
    rm -rf /var/lib/apt/lists/* && \
    systemctl mask systemd-resolved && \
    systemctl enable ssh
