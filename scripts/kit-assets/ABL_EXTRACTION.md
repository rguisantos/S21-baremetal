# Bootloader Samsung: obtenção e triagem estática

Revisado em 2026-10-20. Alvo desta investigação: **SM-G998B / p3s / Exynos 2100**, firmware HZC2. Este guia substitui instruções antigas que confundiam modelos, contêineres e requisitos de carregamento. Não é procedimento de flash.

## Fontes disponíveis e separação correta

- Imagens stock boot.img, vendor_boot.img e dtbo.img já foram recebidas e examinadas; evidências em [stock-firmware-hzc2.md](../../docs/stock-firmware-hzc2.md).
- O pacote Samsung BL é o ponto de partida para inventariar os componentes de firmware de boot; AP fornece imagens como boot/vendor_boot/dtbo. Não assumir que AP contém todos os bootloaders.
- No Exynos, procurar os membros efetivos do pacote, como sboot/Harx quando presentes. Não presumir abl.img, U-Boot, um ELF ou uma cadeia Qualcomm.
- SM-G981 pertence à geração S20; SM-G998B é o S21 Ultra deste projeto. Não usar firmware de outro modelo.

A árvore pública deste projeto não contém sboot.bin, harx.bin ou abl.img. Menções históricas a strings de firmware não substituem os bytes e a análise de referências cruzadas.

## Procedimento offline

1. Inventariar os membros dos pacotes existentes, sem executar firmware nem scripts de instalação. Registrar nome completo, modelo/build e SHA-256 dos contêineres e membros.
2. Separar compressão externa, cabeçalhos Samsung/Android e conteúdo. Manter hashes antes/depois e limites verificáveis; não importar um contêiner inteiro no Ghidra como se fosse código AArch64.
3. Identificar arquitetura, segmentos, endereço de mapeamento e pontos de entrada. ELF fornece metadados; binários brutos exigem reconstrução sustentada por referências e fluxo de controle. Strings e endereços aparentes não bastam para definir base.
4. Localizar as rotinas de leitura de boot/vendor_boot, reconhecimento da Image ARM64, escolha/aplicação de DTB/overlays e alteração de memória/reservas.
5. Seguir as referências até a transferência final de controle. Registrar separadamente PC de destino, x0..x3, EL, permissões timer/ICC, MMU/caches e coerência da imagem. Marcar desconhecido quando a instrução ou o fluxo não demonstrar o valor.
6. Cruzar com o protocolo ARM64 e com as imagens stock, preservando diferenças entre requisito Linux, implementação do firmware e observação no aparelho.

## Ferramentas e limites

O script histórico ../abl_triage.py serve como material de investigação, mas seus leitores de versões/campos ainda precisam de revisão antes de sustentar conclusões. Não tratar sua saída como validação completa de boot headers ou mapa de memória. FDTs brutos podem ser conferidos com ../../scripts/test_fdt.py --inspect em um ambiente executável; tabelas Android precisam ser separadas antes.

O Ghidra pode ajudar a seguir referências ao magic ARM64 e às rotinas de DTB. Ausência/presença de uma string não prova execução nem identidade de uma fase do carregador.

A UART Exynos deve ser conferida contra o driver Samsung e os recursos reais de USI/clock/pinmux. Não escolher PL011, DW8250 ou outra interface por analogia. A coleta Shizuku já encontrou barreiras de permissão e não deve ser repetida esperando acesso root.

## Critério para avançar

Não basta o payload ser relocável ou um repack completar. É necessário comprovar formato aceito, reserva da extensão inteira, estado de entrada e canal de diagnóstico. O resultado da análise Proton e a matriz dessas lacunas estão em [loader-contract.md](../../docs/loader-contract.md).

O Proton recompõe boot e instala vendor_boot; isso não demonstra EL2, posição de carga ou memória livre. Nada neste guia autoriza instalar o R10 no telefone.
