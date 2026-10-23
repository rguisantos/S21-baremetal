# XNU: imagem APFS residente no consumidor EFI

Atualizado em **2026-10-23 (Campo Grande)**. Integramos o disco residente
ao consumidor EFI restrito do laboratório. O teste usa **uma CPU, init
próprio e uma imagem APFS de 4 MiB**: a raiz vem da imagem residente,
enquanto o ramdisk pequeno do payload contém apenas zeros e não é APFS.
A execução anterior do [SpringBoard](hackios-userland-qemu.md) continua
sendo uma referência separada; o userland gráfico completo ainda não foi
executado por este novo consumidor.

## Descritor e papéis

A entrada opcional `resident` do contêiner XNUP tem exatamente 32 bytes,
sem substituir os quatro itens obrigatórios já existentes. Duplicatas,
campos desconhecidos e o antigo `rdres` textual são recusados. A linha de
comando permanece exatamente `cpus=1 loader_return_after=30`.

| Offset | Campo | Formato / política |
|---|---|---|
| 0 | Magic | 8 bytes `S21RDSK\0` |
| 8 | Versão | u32 little-endian, 1 |
| 12 | Flags | u32 little-endian, zero |
| 16 | Endereço físico | u64 little-endian, `0xfc000000` no QEMU |
| 24 | Tamanho do arquivo | u64 little-endian, positivo, múltiplo de 4096, até 3 GiB |

O limite de 3 GiB é uma política do parser, não uma capacidade demonstrada
por esse ensaio de 4 MiB. O endereço precisa coincidir com
`physBase + 0x08000000`; a janela inteira, alinhada, precisa comportar o
kernel, ambos os discos, a árvore, boot_args e a folga prevista. Não há
inferência de endereço ou RAM Samsung.

| Recurso | Papel no contrato capturado |
|---|---|
| Imagem residente | `/chosen/memory-map/RAMDisk`, raiz `/dev/md0` |
| Ramdisk do payload | `RAMDisk1`, `/dev/md1`; 16 KiB de zeros no teste |
| Reserva da imagem | Tamanho arredondado a 16 KiB, dentro da janela linear e abaixo de topOfKernelData |
| Framebuffer, quando presente | Fora da janela do kernel e do payload; páginas conferidas em todos os estágios aplicáveis |

O guard C confere os intervalos dos dois discos contra kernel, árvore e
boot_args antes de copiar segmentos e novamente antes do salto. O leitor
Python confere de modo independente o descritor, as reservas UEFI e os
papéis md0/md1 da árvore capturada. Trocar esses papéis, omitir a declaração
ou alterar seu tamanho causa recusa do verificador.

## Ordem das reservas e leituras

O consumidor agora reserva o payload antes de consultar/configurar o GOP.
Se há descritor residente, escolhe e reserva toda a janela XNU nesse
momento, conservando os bytes já carregados. A configuração gráfica
posterior precisa encontrar páginas fora dessa janela. O percurso sem
descritor mantém a escolha da janela no ponto anterior ao carregamento.

O primeiro acesso ao cabeçalho residente só ocorre depois de conferir a
reserva completa como EfiLoaderData no mapa anterior à cópia. Conferimos
`NXSB`, bloco de 4096 bytes e contagem de blocos correspondente ao tamanho
declarado. Isso é consistência de cabeçalho, **não autenticação da imagem,
verificação do checksum APFS ou prova de disponibilidade anterior à entrada
na aplicação EFI**. O SHA-256 das entradas do ensaio é registrado pelo host.

Os quatro snapshots continuam íntegros e completos:

| Estágio | O que se comprova |
|---|---|
| 0: payload-free | Região de entrada era convencional antes de sua reserva |
| 1: window-free | Payload reservado; janela incluindo imagem residente ainda convencional |
| 2: before-copy | Janela e payload reservados; imagem e framebuffer conferidos antes das cópias |
| 3: handoff | Reservas e conteúdo do cabeçalho continuam válidos antes de cache/handoff |

A antecipação do payload mudou quando o framebuffer aparece nos mapas.
O registro `S21 VIDEO ACQUIRED AFTER 0/1` declara a transição: antes dela,
as páginas devem ser convencionais; depois, EfiLoaderData. O verificador
exige a sequência correspondente, sem escolher uma transição que faça o
teste passar. Registros históricos sem esse campo conservam a política
antiga de EfiLoaderData nos quatro mapas.

## Ensaios

O caso positivo captura, por GDB somente de leitura, boot_args, árvore
Apple e o primeiro bloco da imagem em `arm_init`. Esse bloco precisa ser
idêntico ao da entrada. Depois, o kernel monta md0, executa nosso PID 1,
lê o arquivo de prova, exercita o timer e solicita RB_HALT. O carregador
retorna e emite os mapas completos. A invalidez deliberada do disco pequeno
impede atribuir esse sucesso ao antigo ramdisk embutido.

As recusas QEMU cobrem endereço apontando para o payload, tamanho acima do
limite, magic APFS alterado e uma página da imagem trocada para
EfiBootServicesData depois da reserva. Cada caso deve registrar a recusa
específica e terminar sem cópia de kernel, salto, Darwin ou init.

As suítes de host exercitam o mesmo código C com ASan/UBSan, incluindo
prefixos truncados, versão/flags, alinhamento, overflow, duplicatas,
colisões de layout e tamanho/contagem do cabeçalho. Os testes Python de
vídeo incluem as duas transições de alocação e recusam a fase incorreta.

## Resultados preservados

O [relatório completo](references/xnu-resident-20261023/report.json) contém
fontes/hashes, comandos, mapas e checks. Os [62 testes de host](references/xnu-resident-20261023/host-tests.txt)
passaram: 16 de recursos, 22 de memória, 14 de vídeo e 10 de residente.

| QEMU | Resultado |
|---|---|
| Residente sem display | 29/29 critérios; boot_args/árvore/bloco APFS capturados |
| Residente com ramfb | 30/30; framebuffer fora da janela e adquirido depois do estágio 1 |
| Cabeçalho alterado | 6/6; recusa antes da cópia |
| Página residente reclassificada | 7/7; API de injeção confirmada, sem salto |
| Endereço apontando para o payload | 6/6; descritor recusado antes de ler a imagem |
| Tamanho acima de 3 GiB | 6/6; descritor recusado antes de ler a imagem |
| Compatibilidade: ramdisk embutido com vídeo | 25/25; framebuffer adquirido depois do estágio 0 |
| Compatibilidade: ramdisk embutido sem display | 22/22 |
| Compatibilidade: framebuffer reclassificado | 7/7; recusa preservada |

As duas capturas positivas conservam os 736 bytes de boot_args, a árvore
Apple e o bloco APFS original. Os logs completos estão comprimidos, com
hashes bruto e comprimido registrados. Um ensaio adicional foi interrompido
por timeout de 90 segundos ainda no UEFI, antes da entrada na aplicação;
seu log de 134 bytes foi preservado como `uefi-timeout.txt.gz` e não conta
como PASS. O mesmo caso passou com diretório/NVRAM novos após liberar
arquivos de download já conferidos; não demonstramos causalidade.

## Reprodução

Use os fontes fixados, toolchain e baseline positivo identificados em
[xnu-qemu-lab.md](xnu-qemu-lab.md). O runner cria um diretório novo por caso:

```sh
python3 scripts/run_xnu_resident_lab.py \
  --kernel-tree /caminho/hackios-xnu-kernel \
  --llvm-root /caminho/llvm-extraido \
  --lab-run /caminho/baseline-com-init-proprio \
  --efi-code /caminho/AAVMF_CODE.no-secboot.fd \
  --efi-vars /caminho/AAVMF_VARS.fd \
  --out /caminho/execucao-nova --case positive
```

`--graphics` acrescenta ramfb ao caso positivo. Os outros casos são
`header`, `page-busy`, `input-overlap` e `oversize`. A injeção page-busy
só existe no build experimental escolhido pelo runner e afeta uma página
que a aplicação reservou; o build normal não a executa.

```sh
python3 scripts/test_xnu_efi_resources.py
python3 scripts/test_xnu_efi_memory.py
python3 scripts/test_xnu_video.py
python3 scripts/test_xnu_resident.py
```

## Continuação

A próxima etapa é declarar um perfil explícito para o userland completo:
duração e entrada virtio, memória suficiente para a imagem de 2,5 GB mais
os serviços, e evidência de boot/interface usando esse consumidor. Não
liberamos argumentos arbitrários, SMP ou serviços de hardware para passar
o teste pequeno. O diagnóstico físico, o mapa Samsung e a escolha de boot
Android/XNU continuam pendentes no [roadmap](roadmap.md).
