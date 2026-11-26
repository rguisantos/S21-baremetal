#!/system/bin/sh
# s21xnu-switch.sh — alterna a partição BOOT do SM-G998B entre o boot stock
# e o boot.img do shim s21xnu, sem reparticionar.
#
# Inspirado no DualbootHelper (justin-a30, aec1ea2), que troca boot/recovery
# por cópia com dd. Aqui só a BOOT muda; vendor_boot, recovery, vbmeta e
# GPT ficam intactos (o boot.img do shim depende do vendor_boot stock).
#
# Uso (root no Android ou shell do TWRP; precisa de dd e sha256sum):
#   s21xnu-switch.sh install XNU_BOOT.img   guarda o boot atual (stock) e o do shim em $DIR
#   s21xnu-switch.sh status                 mostra qual imagem está na BOOT
#   s21xnu-switch.sh to-xnu [--no-reboot]   grava o boot do shim e reinicia
#   s21xnu-switch.sh to-android [--no-reboot] regrava o boot stock e reinicia
#
# Volta do XNU/sonda: segurar Volume+ e Power no reinício para entrar no
# TWRP e rodar `sh /cache/s21xnu/s21xnu-switch.sh to-android`.
#
# Variáveis (testes): S21XNU_BOOT_DEV, S21XNU_DIR, S21XNU_REBOOT.
set -u

DIR=${S21XNU_DIR:-/cache/s21xnu}
REBOOT=${S21XNU_REBOOT:-reboot}
STOCK=$DIR/stock-boot.img
XNU=$DIR/xnu-boot.img
SUMS=$DIR/SHA256SUMS

die() { echo "s21xnu-switch: ERRO: $*" >&2; exit 1; }
say() { echo "s21xnu-switch: $*"; }

boot_dev() {
	if [ -n "${S21XNU_BOOT_DEV:-}" ]; then echo "$S21XNU_BOOT_DEV"; return; fi
	for n in boot BOOT; do
		[ -e "/dev/block/by-name/$n" ] && { readlink -f "/dev/block/by-name/$n"; return; }
	done
	die "partição BOOT não encontrada em /dev/block/by-name"
}

size_of() {
	if [ -b "$1" ]; then
		blockdev --getsize64 "$1" 2>/dev/null || cat "/sys/class/block/${1##*/}/size" | awk '{print $1*512}'
	else
		wc -c < "$1" | tr -d ' '
	fi
}

sha() { sha256sum "$1" | cut -d' ' -f1; }

# sha256 dos primeiros N bytes do dispositivo (a partição inteira)
sha_dev() { dd if="$1" bs=4096 count=$(( $2 / 4096 )) 2>/dev/null | sha256sum | cut -d' ' -f1; }

want() { grep " $1\$" "$SUMS" 2>/dev/null | cut -d' ' -f1; }

# Voltar ao Android depende só do backup stock; o shim é conferido apenas
# quando vai ser instalado ou gravado.
check_stock() {
	[ -f "$STOCK" ] && [ -f "$SUMS" ] || die "rode 'install' primeiro (backup stock ausente em $DIR)"
	[ -n "$(want stock-boot.img)" ] && [ "$(sha "$STOCK")" = "$(want stock-boot.img)" ] ||
		die "stock-boot.img não confere com SHA256SUMS"
}

check_xnu() {
	[ -f "$XNU" ] || die "xnu-boot.img ausente em $DIR; rode 'install' de novo"
	[ -n "$(want xnu-boot.img)" ] && [ "$(sha "$XNU")" = "$(want xnu-boot.img)" ] ||
		die "xnu-boot.img não confere com SHA256SUMS; rode 'install' de novo"
}

check_store() { check_stock; check_xnu; }

current() {
	dev=$1; size=$2
	s=$(sha_dev "$dev" "$size")
	if [ "$s" = "$(want stock-boot.img)" ]; then echo stock
	elif [ "$s" = "$(want xnu-boot.img)" ]; then echo xnu
	else echo desconhecido; fi
}

write_verified() {
	img=$1; dev=$2; size=$3
	dd if="$img" of="$dev" bs=4096 conv=fsync 2>/dev/null || die "dd falhou ao gravar $img"
	sync
	[ "$(sha_dev "$dev" "$size")" = "$(sha "$img")" ] || die "verificação após gravar $img falhou: rode o comando oposto ou use o Odin"
}

cmd=${1:-}
DEV=$(boot_dev)
SIZE=$(size_of "$DEV")
[ "$SIZE" -gt 0 ] && [ $(( SIZE % 4096 )) -eq 0 ] || die "tamanho da BOOT inválido: $SIZE"

case "$cmd" in
install)
	src=${2:-}
	[ -f "$src" ] || die "uso: install XNU_BOOT.img"
	[ "$(size_of "$src")" = "$SIZE" ] || die "a imagem precisa ter o tamanho da BOOT ($SIZE bytes); gere com mk_sboot_bootimg.py --avb-lab-key"
	head -c 8 "$src" | grep -q 'ANDROID!' || die "imagem sem magic ANDROID!"
	mkdir -p "$DIR" || die "não consegui criar $DIR"
	if [ -f "$SUMS" ] && [ -f "$STOCK" ]; then
		[ "$(sha "$STOCK")" = "$(want stock-boot.img)" ] || die "backup stock existente não confere; não sobrescrevo"
		say "backup stock já existe; mantido"
	else
		now=$(sha_dev "$DEV" "$SIZE")
		[ "$now" != "$(sha "$src")" ] || die "a BOOT já contém a imagem do shim; instale a partir do Android stock"
		dd if="$DEV" of="$STOCK" bs=4096 count=$(( SIZE / 4096 )) 2>/dev/null || die "falha ao copiar a BOOT"
		[ "$(sha "$STOCK")" = "$now" ] || die "cópia da BOOT não confere"
		echo "$now  stock-boot.img" > "$SUMS"
	fi
	cp "$src" "$XNU.tmp" && mv "$XNU.tmp" "$XNU" || die "falha ao copiar a imagem do shim"
	grep -v ' xnu-boot.img$' "$SUMS" > "$SUMS.tmp"; echo "$(sha "$XNU")  xnu-boot.img" >> "$SUMS.tmp"
	mv "$SUMS.tmp" "$SUMS"
	cp "$0" "$DIR/s21xnu-switch.sh" 2>/dev/null || true
	check_store
	say "instalado em $DIR; BOOT atual: $(current "$DEV" "$SIZE")"
	;;
status)
	check_stock
	( check_xnu ) || say "aviso: imagem do shim indisponível; só 'to-android' funciona"
	say "BOOT ($DEV, $SIZE bytes): $(current "$DEV" "$SIZE")"
	;;
to-xnu|to-android)
	if [ "$cmd" = to-xnu ]; then
		check_store; img=$XNU; from=stock; to=xnu
	else
		check_stock; img=$STOCK; from=xnu; to=stock
	fi
	state=$(current "$DEV" "$SIZE")
	if [ "$state" = "$to" ]; then
		say "BOOT já está em $to"
	elif [ "$state" = "$from" ] || [ "$to" = stock ]; then
		# para voltar ao stock aceita estado desconhecido (gravação interrompida)
		write_verified "$img" "$DEV" "$SIZE"
		say "BOOT agora: $to"
	else
		die "conteúdo da BOOT desconhecido; não gravo o shim sobre ele"
	fi
	[ "${2:-}" = --no-reboot ] || $REBOOT
	;;
*)
	sed -n '2,20p' "$0"
	exit 2
	;;
esac
