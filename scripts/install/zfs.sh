#!/usr/bin/env bash
# Bake the OpenZFS userland into the distro image. The kernel module always
# comes from the host - dockerd's zfs graphdriver only needs the `zfs` binary on
# PATH and an openable /dev/zfs, so a pool the host prepared is unusable without
# these packages inside the container.
#
# Three trip-wires this script exists to route around:
#
#   * The OpenZFS `zfs` RPM carries an ungated `Requires: %{name}-kmod`, so a
#     plain `dnf install zfs` resolves through zfs-dkms and drags in
#     kernel-devel, kernel-debug-core and a DKMS build against a kernel the
#     container never boots: measured at 389 extra packages and 1.44 GB. A
#     dummy package that only *provides* zfs-kmod keeps the same install at 60
#     packages with no kernel package at all. Its version must equal the exact
#     %{version} dnf resolves for `zfs`; a mismatch silently falls back to DKMS.
#     Because that version is pinned, the repository is removed again once the
#     userland is in: leaving it enabled means the next `dnf upgrade` finds a
#     newer zfs whose kmod dependency the dummy no longer satisfies, and the
#     whole DKMS pull returns at deploy time rather than at build time.
#   * Debian keeps zfsutils-linux in contrib, which the base image does not
#     enable. Without the extra source apt reports no installation candidate.
#   * Arch has no zfs userland in core/extra. archzfs publishes a prebuilt
#     zfs-utils, but only on a rolling release tag whose asset filename carries
#     the version, so any pinned URL 404s on the next upstream bump. Building
#     the AUR PKGBUILD (which configures --with-config=user, userland only) is
#     the reproducible route and costs about six minutes. That build runs with
#     --skippgpcheck rather than --skipinteg: the release tarball's sha256 and
#     b2 sums stay verified, and only the detached OpenZFS signature is skipped,
#     because checking it means carrying the release key in the builder's
#     keyring while the same PKGBUILD already supplies both the sums and the
#     list of accepted keys, so the signature adds no trust the sums do not.
set -euo pipefail

RETRIES=3
AUR_BUILDER=pkgbuild
ZFS_RELEASE_FEDORA="3-1 3-0 2-8"
ZFS_RELEASE_EL="3-0 2-8 2-3"

log() { echo "[zfs] $*"; }

# Param: $@ command to run, retried on failure with a widening backoff
retry() {
	local attempt=1
	until "$@"; do
		if [ "${attempt}" -ge "${RETRIES}" ]; then
			log "ERROR: '$*' failed after ${attempt} attempts"
			return 1
		fi
		log "attempt ${attempt} of '$1' failed; retrying"
		sleep $((attempt * 5))
		attempt=$((attempt + 1))
	done
}

install_apt() {
	export DEBIAN_FRONTEND=noninteractive
	local apt_opts=(-o Acquire::Retries="${RETRIES}" -qq)

	if [ "${ID:-}" = debian ]; then
		log "enabling contrib for ${VERSION_CODENAME:?}, which is where zfsutils-linux lives"
		echo "deb http://deb.debian.org/debian ${VERSION_CODENAME} contrib" \
			>/etc/apt/sources.list.d/contrib.list
	fi

	retry apt-get "${apt_opts[@]}" update
	retry apt-get "${apt_opts[@]}" install -y --no-install-recommends zfsutils-linux
	rm -rf /var/lib/apt/lists/*
}

install_pacman() {
	retry pacman -Sy --noconfirm --needed base-devel git

	if ! id "${AUR_BUILDER}" >/dev/null 2>&1; then
		useradd -m -s /bin/bash "${AUR_BUILDER}"
	fi
	install -d -m 0755 /etc/sudoers.d
	printf '%s ALL=(ALL) NOPASSWD: /usr/bin/pacman\n' "${AUR_BUILDER}" \
		>/etc/sudoers.d/99-"${AUR_BUILDER}"-pacman
	chmod 0440 /etc/sudoers.d/99-"${AUR_BUILDER}"-pacman

	local build_root=/tmp/zfs-utils-build
	rm -rf "${build_root}"
	install -d -o "${AUR_BUILDER}" -g "${AUR_BUILDER}" "${build_root}"

	retry su "${AUR_BUILDER}" -c \
		"git clone --depth 1 https://aur.archlinux.org/zfs-utils.git '${build_root}'"
	su "${AUR_BUILDER}" -c \
		"cd '${build_root}' && makepkg --syncdeps --noconfirm --cleanbuild --skippgpcheck"

	local pkg
	pkg="$(find "${build_root}" -maxdepth 1 -type f -name 'zfs-utils-*.pkg.tar.*' \
		! -name '*-debug-*' | head -n1)"
	if [ -z "${pkg}" ]; then
		log "ERROR: makepkg produced no zfs-utils package"
		return 1
	fi

	pacman -U --noconfirm "${pkg}"
	rm -rf "${build_root}" /var/cache/pacman/pkg
}

# Param: $1 path segment of the zfsonlinux repository, `fedora` or `epel`
# Param: $2 space-separated zfs-release versions to try, newest first
release_install() {
	local base="$1" candidates="$2" dist version url
	dist="$(rpm --eval '%{dist}')"
	for version in ${candidates}; do
		url="https://zfsonlinux.org/${base}/zfs-release-${version}${dist}.noarch.rpm"
		if dnf install -y "${url}"; then
			log "zfs-release: ${url}"
			return 0
		fi
		log "no zfs-release ${version} for ${dist}"
	done
	log "ERROR: none of the zfs-release versions '${candidates}' exists for ${dist}"
	return 1
}

install_dnf() {
	case "${ID:-}" in
	fedora) retry release_install fedora "${ZFS_RELEASE_FEDORA}" ;;
	*) retry release_install epel "${ZFS_RELEASE_EL}" ;;
	esac

	local zfs_version
	zfs_version="$(dnf --quiet repoquery --qf '%{version}\n' zfs | sort -V | tail -n1)"
	if [ -z "${zfs_version}" ]; then
		log "ERROR: the zfs-release repository offers no zfs package"
		return 1
	fi
	log "zfs userland offered by the repository: ${zfs_version}"

	if ! command -v rpmbuild >/dev/null 2>&1; then
		retry dnf install -y rpm-build
	fi

	local topdir=/tmp/zfs-kmod-container
	rm -rf "${topdir}"
	mkdir -p "${topdir}/SPECS"
	cat >"${topdir}/SPECS/zfs-kmod-container.spec" <<SPEC
Name:      zfs-kmod-container
Version:   ${zfs_version}
Release:   1
Summary:   Satisfies the zfs kernel module dependency inside a container
License:   CDDL
BuildArch: noarch
Provides:  zfs-kmod = ${zfs_version}

%description
The container never loads a zfs module; the host supplies it and the container
reaches it through /dev/zfs. This package exists only so the zfs userland
resolves without pulling a DKMS toolchain and a kernel it will never boot.

%files
SPEC

	rpmbuild --define "_topdir ${topdir}" -bb "${topdir}/SPECS/zfs-kmod-container.spec"
	dnf install -y "${topdir}"/RPMS/noarch/zfs-kmod-container-*.rpm
	retry dnf install -y zfs

	if rpm -qa 'kernel-devel*' 'kernel-debug*' 'zfs-dkms' | grep -q .; then
		log "ERROR: the transaction pulled kernel or DKMS packages, so the dummy did not take"
		rpm -qa 'kernel-devel*' 'kernel-debug*' 'zfs-dkms' >&2
		return 1
	fi

	dnf remove -y zfs-release
	rm -rf "${topdir}"
	dnf clean all
}

verify() {
	local tool
	for tool in zfs zpool; do
		if ! command -v "${tool}" >/dev/null 2>&1; then
			log "ERROR: ${tool} is missing after the install"
			return 1
		fi
	done

	if ldd "$(command -v zpool)" | grep -q 'not found'; then
		log "ERROR: zpool has unresolved shared libraries"
		ldd "$(command -v zpool)" | grep 'not found' >&2
		return 1
	fi

	if command -v dnf >/dev/null 2>&1 && dnf repolist --enabled 2>/dev/null | grep -q '^zfs'; then
		log "ERROR: a zfs repository is still enabled, so an upgrade would re-resolve the kmod"
		return 1
	fi

	log "installed $(command -v zfs) and $(command -v zpool); all libraries resolved"
}

main() {
	# shellcheck source=/dev/null
	. /etc/os-release

	if command -v apt-get >/dev/null 2>&1; then
		install_apt
	elif command -v pacman >/dev/null 2>&1; then
		install_pacman
	elif command -v dnf >/dev/null 2>&1; then
		install_dnf
	else
		log "ERROR: no supported package manager (apt/pacman/dnf)"
		exit 1
	fi

	verify
}

main "$@"
