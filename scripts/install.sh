#!/bin/sh
# Omit --version to install the latest stable release; explicit tags also work.
set -eu
umask 077
fail() { printf '%s\n' "tofa: $*" >&2; exit 1; }
version=latest
modify_path=yes
while [ "$#" -gt 0 ]; do
 case "$1" in
  --version) [ "$#" -ge 2 ] || fail '--version requires a tag'; version=$2; shift 2 ;;
  --no-modify-path) modify_path=no; shift ;;
  *) fail "unknown option: $1" ;;
 esac
done
case "$version" in ''|*[!A-Za-z0-9._-]*) fail 'invalid release tag';; esac
case "$(uname -s)" in Darwin) platform=darwin;; Linux) platform=linux;; *) fail 'use install.ps1 on Windows';; esac
case "$(uname -m)" in arm64|aarch64) arch=arm64;; x86_64|amd64) arch=amd64;; *) fail 'unsupported architecture';; esac
: "${HOME:?HOME is required}"
root=${TOFA_INSTALL_DIR:-"$HOME/.local/share/tofa"}
case "$root" in /*) ;; *) fail 'install directory must be absolute';; esac
case "$root" in *'
'*) fail 'newlines in paths are unsupported';; esac
[ ! -L "$root/.tofa-install" ] && [ ! -L "$root/.path-files" ] || fail 'refusing symlink ownership metadata'
[ ! -L "$root" ] || fail 'install directory must not be a symlink'
if [ -d "$root" ] && [ ! -f "$root/.tofa-install" ]; then
 [ -z "$(ls -A "$root")" ] || fail 'existing installation directory is not owned by tofa'
fi
if [ -f "$root/.tofa-install" ]; then [ "$(cat "$root/.tofa-install")" = tofa-install-v1 ] || fail 'unknown install manifest'; fi
if [ "$version" = latest ]; then
 # Resolve GitHub's stable-release redirect once, without a JSON parser runtime.
 resolved=$(curl -fsSL --proto '=https' --proto-redir '=https' --connect-timeout 15 --max-time 60 \
  -o /dev/null -w '%{url_effective}' https://github.com/kreuzhofer/tofa-launcher/releases/latest) \
  || fail 'could not resolve latest stable release; retry or select an existing --version'
 case "$resolved" in
  https://github.com/kreuzhofer/tofa-launcher/releases/tag/*) version=${resolved##*/} ;;
  *) fail 'invalid latest stable release URL' ;;
 esac
 # Reject extra path components, query strings, newlines and prerelease tags.
 [ "$resolved" = "https://github.com/kreuzhofer/tofa-launcher/releases/tag/$version" ] || fail 'invalid latest stable release URL'
 case "$version" in ''|*[!0-9.v]*) fail 'invalid latest stable release tag' ;; esac
 printf '%s\n' "$version" | grep -Eq '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$' \
  || fail 'invalid latest stable release tag'
fi
asset="tofa_${version}_${platform}_${arch}"
base=${TOFA_RELEASE_BASE_URL:-"https://github.com/kreuzhofer/tofa-launcher/releases/download/$version"}
work=$(mktemp -d);trap 'rm -rf "$work"' EXIT HUP INT TERM
curl -fsSL --proto '=https,file' --proto-redir '=https' "$base/$asset" -o "$work/tofa"
curl -fsSL --proto '=https,file' --proto-redir '=https' "$base/SHA256SUMS" -o "$work/SHA256SUMS"
expected=$(awk -v file="$asset" '
 $2 == file {
  count++
  if (NF != 2 || length($1) != 64 || $1 ~ /[^0-9a-fA-F]/) invalid=1
  sum=tolower($1)
 }
 END { if (count != 1 || invalid) exit 1; print sum }
' "$work/SHA256SUMS") || fail 'missing, invalid or ambiguous SHA256 checksum'
if command -v sha256sum >/dev/null 2>&1; then actual=$(sha256sum "$work/tofa" | awk '{print $1}');else actual=$(shasum -a 256 "$work/tofa" | awk '{print $1}');fi
[ "$expected" = "$actual" ] || fail 'checksum mismatch; existing installation retained'
mkdir -p "$root/bin"
[ ! -L "$root/bin" ] && [ ! -L "$root/bin/tofa" ] || fail 'refusing symlink in installation'
printf '%s\n' tofa-install-v1 > "$root/.tofa-install"
config=${XDG_CONFIG_HOME:-"$HOME/.config"}/tofa
[ ! -L "$config/desktop-bridge-v1" ] && [ ! -L "$config/desktop-bridge-v2" ] || fail 'refusing symlink desktop integration'
# Existing saved desktop references need a lease and a compatible helper update.
# A clean installation creates the bridge on its first qualified desktop launch.
if [ "$platform" = darwin ] && { [ -e "$config/desktop-bridge-v1" ] || [ -e "$config/desktop-bridge-v2" ]; }; then
 chmod 700 "$work/tofa"
 "$work/tofa" desktop-lifecycle install "$root" || fail 'desktop upgrade stopped; existing installation retained; resolve the reported ownership or compatibility problem and retry'
else
# Stage on the target filesystem so replacement is atomic.
staged=$(mktemp "$root/bin/.tofa.XXXXXX")
cp "$work/tofa" "$staged"
chmod 755 "$staged"
mv -f "$staged" "$root/bin/tofa"
fi
quote() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }
bin=$(quote "$root/bin")
activation="export PATH=$bin:\"\$PATH\""
shell_name=${SHELL:-sh}
shell_name=${shell_name##*/}
if [ "$shell_name" = fish ]; then activation="fish_add_path --path $bin";fi
append_path() {
 rc=$1
 if [ -L "$rc" ];then printf '%s\n' "Skipping symlink startup file: $rc" >&2;return 1;fi
 mkdir -p "$(dirname "$rc")" || return 1
 if [ ! -f "$rc" ] || ! grep -Fq '# >>> tofa >>>' "$rc";then
  printf '\n# >>> tofa >>>\n%s\n# <<< tofa <<<\n' "$activation" >> "$rc" || return 1
  printf '%s\n' "$rc" >> "$root/.path-files" || return 1
 fi
}
path_failed=no
if [ "$modify_path" = yes ];then
 case "$shell_name" in
  zsh) append_path "${ZDOTDIR:-$HOME}/.zshrc" || path_failed=yes ;;
  bash)
   append_path "$HOME/.bashrc" || path_failed=yes
   if [ -f "$HOME/.bash_profile" ];then append_path "$HOME/.bash_profile" || path_failed=yes
   elif [ -f "$HOME/.bash_login" ];then append_path "$HOME/.bash_login" || path_failed=yes
   else append_path "$HOME/.profile" || path_failed=yes;fi ;;
  fish) append_path "${XDG_CONFIG_HOME:-$HOME/.config}/fish/conf.d/tofa.fish" || path_failed=yes ;;
  *) printf '%s\n' 'Shell not recognized. Add the activation line below to your shell startup file.' ;;
 esac
fi
printf '\nInstalled tofa %s in %s\nActivate in this terminal:\n  %s\n' "$version" "$root/bin" "$activation"
if [ "$modify_path" = no ] || [ "$path_failed" = yes ] || { [ "$shell_name" != zsh ] && [ "$shell_name" != bash ] && [ "$shell_name" != fish ]; };then
 case "$shell_name" in
  zsh) fallback_rc=${ZDOTDIR:-$HOME}/.zshrc ;;
  fish) fallback_rc=${XDG_CONFIG_HOME:-$HOME/.config}/fish/conf.d/tofa.fish ;;
  *) fallback_rc=$HOME/.profile ;;
 esac
 printf '%s\n' 'If needed, resolve startup-file permissions, then persist and activate with this one line:'
 printf '  mkdir -p %s; printf "%%s\\n" %s %s %s >> %s; printf "%%s\\n" %s >> %s; %s\n' \
  "$(quote "$(dirname "$fallback_rc")")" "$(quote '# >>> tofa >>>')" "$(quote "$activation")" "$(quote '# <<< tofa <<<')" \
  "$(quote "$fallback_rc")" "$(quote "$fallback_rc")" "$(quote "$root/.path-files")" "$activation"
fi
printf '%s\n' 'Then run: tofa auth login'
