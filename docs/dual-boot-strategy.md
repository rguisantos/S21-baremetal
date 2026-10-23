# Objetivo: escolha entre Android e XNU/userland iOS no S21

Direção aprovada pelo usuário em **2026-10-22**. Queremos investigar uma
forma de escolher qual ambiente iniciar no SM-G998B/p3s: o Android já
utilizado e, futuramente, XNU com userland iOS adaptado. **A seleção de boot
no aparelho ainda não existe.** O primeiro avanço dessa frente é o
[XNU no QEMU com programa próprio](xnu-qemu-lab.md). O
[contrato binário](xnu-boot-contract.md) já tem codec, layout conferido e
captura validada no laboratório. O [adaptador de recursos](xnu-fdt-adapter.md)
já projeta CPU/GIC/PSCI/timer do FDT. A [interface iOS 16.5](hackios-userland-qemu.md)
foi reproduzida no QEMU com navegação em Ajustes; a adaptação física continua aberta.

## Contratos dos dois caminhos

Uma escolha de sistema precisa selecionar um contrato de carga completo,
incluindo imagem, argumentos, memória e serviços disponíveis.

| Aspecto | Android stock HZC2 | Experimento XNU |
|---|---|---|
| Executável | Linux ARM64 Image nas imagens de boot v3 recebidas | Mach-O arm64; contêiner XNUP no laboratório upstream |
| Argumento de entrada | FDT bruto em x0 no trecho LK estudado; conteúdo final dinâmico ainda aberto | x0 aponta para boot_args XNU, que referencia árvore Apple e buffers válidos |
| Memória | Ajustes LK/Harx, reservas e initrd próprios; reconstrução em andamento | Janela do kernel, ramdisk, argumentos, árvore e memória do carregador com posse demonstrada |
| Serviços de entrada | Estado de EL/MMU/cache e permissões por confirmar no salto físico | Adaptar ao estado Samsung observado; permissões GIC/timer e coerência precisam ser comprovadas |
| Armazenamento | Manter artefatos Android identificados e coerentes com a cadeia Samsung | Inicialmente imagem APFS de laboratório; percurso físico e persistência ainda por definir |
| Observação | Coleta shell limitada; UART/log físico pendente | Log/retorno funcionando no QEMU; backend Samsung pendente |

O payload R10 recebe FDT e não deve receber boot_args XNU. Converter apenas
um endereço ou renomear o contêiner não resolve a diferença. Um futuro
carregador pode compartilhar validação de intervalos e política de memória,
mas os adaptadores de entrada têm de continuar explícitos.

## Marcos até uma escolha de boot

| Marco | Critério | Estado |
|---|---|---|
| D0 — base de laboratório | XNU inicia, executa programa próprio e entrega resultado; controle negativo recusado | **Concluído no QEMU**, com kernel prebuilt e variante EFI recompilada; não é iOS gráfico |
| D1 — entrada Samsung observável | Diagnóstico mínimo no S21 e registro recuperado; região/coerência e percurso de carga demonstrados | Pendente; Marco A do roadmap principal |
| D2 — adaptação XNU | boot_args/árvore Apple/memória gerados e conferidos; XNU em uma CPU no S21 com log recuperado | Parcial: codec, projeção e consumidor EFI executados no QEMU; memória/entrada Samsung e execução física dependem de D1 |
| D3 — userland e interface | Serviços e APFS primeiro no laboratório; depois framebuffer/CPU no S21 e periféricos próprios | Parcial: SpringBoard/Ajustes/Geral/Sobre conferidos no QEMU de referência; integração ao consumidor restrito e execução Samsung pendentes |
| D4 — escolha Android/XNU | Dois caminhos iniciam individualmente; seleção, retorno/recuperação e armazenamento têm testes próprios | Pendente |

A implementação de D4 depende do caminho que a investigação Samsung
demonstrar. Não presumir UEFI/fastboot Qualcomm, slots A/B, espaço livre,
uma nova partição ou a possibilidade de retornar ao Android sem reinício.
Os endereços e protocolos do POCO não definem esse mecanismo.

O primeiro ensaio físico continua sendo o diagnóstico mínimo com resultado
recuperável. Um menu não substitui essa evidência. Para alcançar D3, ainda
serão necessários serviços e drivers além do kernel: display/touch,
armazenamento, energia e, posteriormente, GPU e comunicação.

## Próxima entrega

O marco seguinte à [integração EFI](xnu-efi-adapter-lab.md), a
[validação das reservas UEFI](xnu-uefi-memory.md), foi executado: payload e
janela reservados, quatro mapas capturados, 22 critérios positivos e oito
recusas. Passaram 22 testes de memória/evidência e os 16 de recursos.
O contrato agora usa o mapa UEFI observado para conferir os buffers.
Os recursos periféricos continuam no perfil QEMU fixado; ampliar esse
perfil exige origem e contraprovas próprias. A base HZC2 permanece recusada
para memória por ausência de bancos RAM e reservas incompletas. Ainda não
há plano físico ou adaptador executável Samsung.

Em paralelo, P1/P2 do [roadmap principal](roadmap.md) seguem na cadeia de
entrada, coerência, observação e memória Samsung. Não é necessário reenviar
firmware. O laboratório não modifica Android, partições ou arquivos
recebidos do aparelho.
