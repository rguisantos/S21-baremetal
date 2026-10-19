#!/usr/bin/env bash
# ============================================================================
# snapshot_project.sh — pacote versionado do projeto (política: SEMPRE, vN)
# ----------------------------------------------------------------------------
# Uso:   snapshot_project.sh <VERSAO> [opções]
#        ex.:  scripts/snapshot_project.sh v7
#              scripts/snapshot_project.sh v7 --with-toolchain
#              scripts/snapshot_project.sh v7 --force
#
# PRODUZ (padrão — "arquivos necessários", ~75 MB):
#   download/exynos-baremetal-v<N>.tar.gz   +  .sha256
#
#   Conteúdo: código F1/F2, kits DAY1/DAY2 (diretórios), payloads, sweeps
#   e dumps de experimento (.exc/.log), análise (abl_triage.py,
#   ABL_EXTRACTION.md), repacks blindados, magiskboot, worklog.md, .env,
#   .gitignore — TUDO o que o projeto criou.
#
#   FORA (por decisão do usuário — "2.4gb é muito"):
#   - scripts/toolchain/{env,root,qemu-root,debs,bin}  (reconstituível via
#     kit-assets/SETUP.md + toolchain/fetch_qemu.sh — zero perda intelectual)
#   - .git, skills/, upload/                           (ambiente da sessão)
#
#   --with-toolchain: inclui o toolchain completo no MESMO tar (vira ~1 GB;
#   usar só quando a máquina de destino não puder baixar dependências).
#
# ANTI-ANINHAMENTO (crítico): download/*.tar.gz|*.tar|*.sha256|*.tar.md5 são
#   excluídos — sem isso, v(N) conteria v(N-1) e o pacote cresceria
#   exponencialmente a cada round. O conteúdo dos kits entra pelos
#   DIRETÓRIOS, nunca pelos tars.
#
# BLINDAGEM (ética do projeto — cf. armadilha 14 do worklog):
#   - gzip -t após o tar (integridade verificada, não presumida)
#   - .sha256 re-lido do ARQUIVO (não de variável de shell)
#   - recusa overwrite sem --force
#   - versão = número do round (v6 = R6/Dia 2) → próximo round = v7
# ============================================================================
set -euo pipefail

VER="${1:?Uso: $0 <VERSAO> [--with-toolchain|--force]  (ex.: $0 v7)}"
shift || true
WITH_TC=0
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --with-toolchain) WITH_TC=1 ;;
    --force)          FORCE=1 ;;
    *) echo "Opção desconhecida: $arg" >&2; exit 1 ;;
  esac
done

ROOT="/home/z/my-project"
OUT="$ROOT/download"
PKG="$OUT/exynos-baremetal-${VER}.tar.gz"

stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
T0=$(date +%s)

if [[ -e "$PKG" && $FORCE -eq 0 ]]; then
  echo "ERRO: $PKG já existe. Apague-o ou use --force." >&2
  exit 1
fi

EXCLUDES=(
  -C "$ROOT"
  --exclude='.git'
  --exclude='skills'
  --exclude='upload'
  --exclude='download/*.tar.gz'
  --exclude='download/*.tar'
  --exclude='download/*.tar.md5'
  --exclude='download/*.sha256'
)
[[ $WITH_TC -eq 0 ]] && EXCLUDES+=(
  --exclude='scripts/toolchain/env'
  --exclude='scripts/toolchain/root'
  --exclude='scripts/toolchain/qemu-root'
  --exclude='scripts/toolchain/debs'
  --exclude='scripts/toolchain/bin'
)

MODE="arquivos necessários"
[[ $WITH_TC -eq 1 ]] && MODE="COMPLETO c/ toolchain (~1 GB)"

echo "[$(stamp)] Pacote ${VER} — ${MODE}"

tar -czf "$PKG" "${EXCLUDES[@]}" worklog.md .gitignore .env scripts download

# --- verificação tripla ---
gzip -t "$PKG" || { echo "gzip -t FALHOU: $PKG" >&2; exit 1; }
echo "  gzip -t: OK"
sha256sum "$PKG" > "$PKG.sha256"
SUM=$(cut -d' ' -f1 < "$PKG.sha256")     # re-lê do arquivo (armadilha 14)
echo "  sha256: $SUM"
NFILES=$(tar -tzf "$PKG" | wc -l)
echo "  conteúdo: ${NFILES} arquivos, $(du -h "$PKG" | cut -f1)"

echo "[$(stamp)] v${VER#v} pronto em ${T0:+$(( $(date +%s) - T0 ))}s → $PKG (+ .sha256)"
