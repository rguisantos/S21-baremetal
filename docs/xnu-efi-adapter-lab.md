# Adaptador consumido pela EFI no QEMU

Esta página registra a integração inicial. A [continuação de memória UEFI](xnu-uefi-memory.md)
reserva também o payload, captura quatro mapas completos e amplia o runner
para **22 critérios positivos e oito recusas**, com 22 testes de memória/evidência
e os 16 testes de recursos. Os números e manifestos abaixo são do primeiro marco.

Marco de **2026-10-22, Campo Grande**. Compilamos uma variante do carregador
EFI HackiOS que recebe o fragmento de recursos Apple pelo payload, valida
seu conteúdo e o usa para construir a árvore entregue ao XNU. O caso
positivo satisfez **20 critérios**; outras **cinco execuções recusaram
entradas antes da cópia dos segmentos para a janela XNU e do salto**. Os mesmos validadores C
passaram **16 testes de host** com ASan/UBSan.

O carregador foi compilado dos fontes; o **kernel continua sendo o prebuilt
fixado**, executando nosso init Darwin. Esta etapa não executou userland
iOS, SpringBoard, Samsung ou SMP.

## Caminho exercitado

1. Uma fixture FDT sintética declara RAM de 6 GiB, uma CPU, GIC, PSCI HVC
   e contador de 62,5 MHz. Não é dump QEMU ou descrição do S21.
2. O adaptador existente cruza os leitores FDT e projeta os recursos. O
   perfil de laboratório acrescenta explicitamente a UART PL011 QEMU.
   O fragmento resultante tem **908 bytes**.
3. O payload XNUP inclui kernel, ramdisk, cmdline fixa e a entrada `adtres`.
   O parser C limita tamanhos, nomes, duplicidades, padding e bounds Mach-O.
4. A EFI decodifica o fragmento, exige o perfil QEMU em uma CPU e compara
   frequência/MPIDR declarados com os registradores no instante observado.
5. O carregador mantém a seleção/reserva UEFI de sua janela. A checagem C
   recusa sobreposição entre kernel, ramdisk, árvore, argumentos e payload.
6. O writer upstream usa os valores consumidos, incluindo o tamanho GICR.
   Um breakpoint somente de leitura em arm_init confere os dados entregues;
   depois a execução retoma até init, APFS, timer, RB_HALT e retorno normal.

As marcas nativas precedem o salto:

```text
S21 XNU ADAPTER: resources PASS frequency 62500000 GICR size 100000
S21 XNU ADAPTER: layout PASS before jump
```

UEFI permanece residente, como no desenho upstream. O breakpoint em
`0xfffffff007453994` pertence somente ao kernel identificado por hash.
x0 já é virtual nesse estágio C; não mede a entrada Samsung com MMU
desligada. O debugger consulta memória/registradores e usa breakpoint de
execução; não injeta a árvore ou altera argumentos.

## Contraprovas no carregador

| Caso | Recusa observada | Resultado |
|---|---|---|
| [Fragmento truncado](references/xnu-efi-truncated-20261022.txt) | REJECT resources | Sem cópia/salto/Darwin/init |
| [Frequência declarada alterada](references/xnu-efi-counter-20261022.txt) | REJECT resources | Sem cópia/salto/Darwin/init |
| [Redistributor fora do perfil](references/xnu-efi-gic-20261022.txt) | REJECT resources | Sem cópia/salto/Darwin/init |
| [Entrada payload duplicada](references/xnu-efi-duplicate-20261022.txt) | REJECT payload | Sem cópia/salto/Darwin/init |
| [Comando Mach-O com tamanho zero](references/xnu-efi-kernel-bounds-20261022.txt) | REJECT payload | Sem cópia/salto/Darwin/init |

Todos os seis QEMU saíram 0. Nas recusas, isso significa encerramento do
carregador: o harness exige a marca de recusa e ausência das fases
posteriores. Encontrar somente exit zero não conta como boot válido.
Os 20 critérios positivos são os 17 do init anterior mais três verificações
das marcas nativas; não são 20 boots. A captura verifica também os campos
GIC/CPU/PSCI/contador/I/O/UART e reemissão exata dos buffers de 736 e 14800 bytes.

## Código e limites

- `lab/xnu/efi_resources.c/.h`: consumidor freestanding do perfil canônico
  de uma CPU, parser XNUP, bounds Mach-O e intervalos físicos.
- `lab/xnu/efi_lab.py`: fixture explícita, empacotador e adaptação por
  âncoras do fonte upstream verificado. Compila cópia nova, sem editar o clone.
- `scripts/run_xnu_adapter_lab.py`: compila, executa seis casos e captura
  somente o positivo; produz comandos, hashes, logs e relatórios.
- `scripts/test_xnu_efi_resources.py`: 16 testes do mesmo C, incluindo todos
  os prefixos truncados, tipos/valores incompatíveis, payload e memória.

O consumidor C exige a ordem/contagem do fragmento de laboratório. Não é
um leitor geral da árvore Apple. Exige GICD 0x08000000/0x10000, GICR
0x080a0000/0x100000, UART 0x09000000/0x1000, HVC, MPIDR 0 e 62,5 MHz.
O teste de host confirma a recusa do fragmento HZC2 de oito CPUs/SMC.
O adaptador Samsung anterior continua preservando GICR de **2 MiB**.

O kernel é uma entrada confiada pelo runner por SHA-256. O consumidor
confere estrutura/bounds; não autentica assinatura ou oferece um loader
geral de executáveis. A linha aceita não ativa os caminhos de periféricos
do telefone existentes no fonte upstream.

A reserva UEFI da janela foi observada nesse primeiro ensaio. O mapa completo de
reservas do firmware ainda não havia sido capturado; isso foi feito na
[etapa seguinte](xnu-uefi-memory.md). A fixture declara memória; nenhum
resultado transfere sua propriedade ou permissões ao Samsung. Todos os
relatórios conservam `hardware_ready: false`.

## Compilar e reproduzir

Use os clones/UEFI fixados no [laboratório anterior](xnu-qemu-lab.md).
Clang/LLD 19.1.7 e dependências foram extraídos de pacotes Debian, sem
instalação no sistema ou SDK Apple; versões, URLs e hashes estão no
[manifesto da ferramenta](references/xnu-efi-toolchain-20261022.json).
Verifique os SHA-256 e extraia os pacotes LLVM com `dpkg-deb -x` numa raiz
própria. O wrapper limita o caminho de bibliotecas aos subprocessos de build;
dependências dinâmicas restantes vêm do host documentado no manifesto.

```sh
python3 scripts/test_xnu_efi_resources.py
python3 scripts/test_xnu_efi_memory.py
python3 scripts/run_xnu_adapter_lab.py \
  --lab-run /caminho/ensaio-positivo-anterior \
  --kernel-tree /caminho/hackios-xnu-kernel \
  --llvm-root /caminho/llvm-extraido \
  --efi-code /caminho/AAVMF_CODE.no-secboot.fd \
  --efi-vars /caminho/AAVMF_VARS.fd \
  --out /caminho/nova-execucao
```

O runner exige baseline positivo, kernel/UEFI identificados e saída nova.
Cada caso tem NVRAM/FAT próprios, rede desativada e prazo limitado. Os
binários e árvores brutas ficam fora do Git. Na versão atual, o runner
executa também três falhas de memória; consulte a [validação UEFI](xnu-uefi-memory.md).
O
[manifesto da execução](references/xnu-efi-adapter-20261022.json) conserva
hashes, critérios e seis transcrições completas em texto escapado.
O [serial positivo](references/xnu-efi-positive-20261022.txt) registra o
diagnóstico Darwin e seu retorno na mesma sessão.

X2 agora tem integração executada no carregador de laboratório. O próximo
trabalho é ampliar a entrada de recursos no consumidor sem perder as
recusas e a proveniência. O caminho Samsung ainda depende de entrada,
coerência, RAM/reservas efetivas e observação definidos em P1/P2 do
[roadmap](roadmap.md). Esta variante não é um artefato de flash/chainload S21.
