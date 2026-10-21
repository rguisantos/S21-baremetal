# Validação reproduzida em 2026-10-20

Revisão que adiciona parser/política FDT e atualiza a documentação. Ambiente Linux x86_64; GCC AArch64 14.2 e QEMU 10.0.13 locais, compilador C nativo com ASan/UBSan. Esta página registra resultados observados; os logs completos são gerados localmente pelos comandos abaixo e não são prova de execução no Exynos.

| Verificação | Resultado observado |
|---|---|
| `make -C r8 -j4 all` | Cinco ELFs e disassemblies gerados |
| `make -C r8 regress` | R8A, R8B, R8C e R9: 4/4 PASS |
| `python3 scripts/test_fdt.py` | FDT MODEL PASS: 43 casos, ASan/UBSan |
| Inspeção FDT do firmware | Base HZC2 + oito árvores com overlay: parsing OK; boot -4 por falta de RAM |
| Inspeção FDT TWRP | Parsing OK após retirar tabela de 64 bytes; boot -4 por falta de RAM |
| `bash scripts/test_pr_fixes.sh` | UART PASS em dois modos; ATOMIC PASS em AArch64/QEMU |
| `bash scripts/test_r10_stage.sh` | Modelos GIC/exceções PASS; boot, FDT, cinco IRQs e parada fatal esperada no QEMU |
| `bash shim/build.sh` | shim.elf e shim.bin gerados; execução não testada |
| Parser C | Compilação adicional C11 com Wall/Wextra/Werror/pedantic, sem diagnóstico |
| ELF R10 | Pilhas dentro de data PT_LOAD; payload total termina em 0x800c4000 nesta compilação |

Assinaturas da integração R10:

```text
GIC MODEL PASS
EXCEPTION MODEL PASS
R10 BOOT PASS: FDT, BSS, EL1
R10 FDT PASS: resources and complete payload extent
R10 TIMER PASS: five IRQs through production dispatcher
R10 FATAL kind=0x0 ELR=0x400811a0 ESR=0x2000000 FAR=0x0
```

O fault final vem de uma instrução indefinida intencional; o harness exige timeout/park e ausência de FAIL. Endereços de código podem mudar entre compilações. A frequência do timer no QEMU é a do emulador, não os 26 MHz descritos no DTB stock. O fixture do teste fornece RAM/GIC de QEMU e não é uma árvore para carregar no telefone.

Na inspeção ELF com `readelf -lW r8/build/r10_payload.elf`, a imagem tem segmentos RX e RW; o segmento RW inclui `.bss .stacks`, p_memsz=0x3e000 a partir de 0x80086000. Esse tamanho descreve o artefato, não autoriza usar o endereço no aparelho. O carregador deve reservar p_memsz antes de escrever imagem/BSS/pilhas.

Continuam warnings preexistentes: parâmetro não usado no MCT, comparações signed/unsigned no SMP dormente e segmentos RWX nos módulos didáticos R8/R9. O R10 não ativa esses drivers experimentais na main. As verificações de software não demonstram o handoff Samsung, permissões de acesso reais ou configuração USI/cache do telefone.

Para repetir a inspeção com suas próprias cópias das imagens, separe o FDT bruto da tabela Android, aplique cada overlay com `fdtoverlay` e use `scripts/test_fdt.py --inspect`. Identidade e offsets dos arquivos recebidos estão em [stock-firmware-hzc2.md](stock-firmware-hzc2.md); a referência TWRP está em [twrp-reference.md](twrp-reference.md). Os diagnósticos privados do aparelho não foram incluídos no repositório.

## Complemento: contêiner e Proton publicado

O empacotador/consumidor S21R10 passou inicialmente em 59 casos (60 após a regressão adicional de kernel_end relativo), incluindo inspeção C com ASan/UBSan e extensão do ELF real até o fim das pilhas. O shim recompila com handoff desativado e entrada padrão em park. O ZIP público Proton foi baixado e seu SHA-256 conferido; detalhes em [proton-binary.md](proton-binary.md). Isso não é validação de SMP ou carregamento no telefone.

## Carregador EL2 com main de produção

`python3 scripts/test_payload_stage.py`: 17 casos ASan/UBSan, verificando cópia/zero exatos e recusa sem alterar destino. `python3 scripts/test_payload_loader.py`: um handoff EL2→EL1 com main/parser/GIC/timer/dispatcher reais, mais cinco recusas. GDB confere a janela inteira antes do salto e símbolos/IRQs depois dele; UART é o backend QEMU. Não foram usados sockets, SMP ou hardware Samsung. Detalhes em [qemu-el2-loader.md](qemu-el2-loader.md).
