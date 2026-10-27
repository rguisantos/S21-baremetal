# Diagnóstico Samsung: percurso de carga e recuperação

Consolidação em **2026-10-26 (Campo Grande)**, base main `b70c3a9` após
PR #33. Não houve acesso ao telefone ou execução de firmware nesta entrega.
Os READMEs Kernel/Platform recebidos foram relidos: descrevem compilação,
não fornecem um transporte de carga/leitura ou estado de entrada.

**Nenhum percurso físico completo está demonstrado nas condições informadas.**
A cópia/salto LK têm evidências estáticas; a Image própria e seu registro têm
testes QEMU. Entre esses resultados faltam aceitação da imagem, posse/coerência
e aquisição dos bytes. Esta matriz não autoriza uma tentativa física.

## Contexto e referências

O último estado informado pelo usuário é SM-G998B/p3s, Exynos 2100, build
G998BXXSJHZC2/Android 15, sem root e bootloader travado. É um relato anterior,
não uma nova medição. Rish/Shizuku operou como uid=2000 e várias leituras
foram negadas; o bugreport posterior recuperou logs stock. Estado Knox não
substitui a comprovação de um caminho que aceite uma imagem própria.

A documentação [AOSP sobre estado do dispositivo](https://source.android.com/docs/security/features/verifiedboot/device-state)
descreve verificação da raiz de confiança no estado LOCKED. É uma regra de
referência Android, não uma reconstrução de todos os validadores Samsung.
[Transições de estado](https://source.android.com/docs/core/architecture/bootloader/locking_unlocking)
não são mecanismo de preservação de RAM. Os comandos genéricos dessas páginas
não foram validados como interface deste Samsung e não são instruções desta entrega.

As evidências Samsung abaixo usam o sboot já recebido, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Endereços de instrução são offsets no arquivo; valores AP/RAM são nominais
quando não houver observação explícita. Não foram relidos registradores físicos.

## Matriz do Marco A

| Requisito | Evidência disponível | Lacuna para execução física |
|---|---|---|
| Identidade e acesso | [Relato/coleta shell](runtime-collection.md), [bugreport HZC2](dram-observed-hzc2.md); último estado sem root/travado | Nenhum acesso novo ou caminho de imagem própria demonstrado |
| Artefato | [Diagnóstico](entry-diagnostic.md): Image ARM64 bruto, registro final de 128 bytes, sem EFI/Android/assinatura Samsung | Header ARM64 não é um boot.img aceito pelo telefone |
| Contêiner/cópia | [Stock v3](stock-firmware-hzc2.md), [cópia LK](lk-kernel-copy.md): 0x12e88c copia kernel_size de boot+header arredondado | Autenticação, todos os ramos e efeitos de 0x151b10 ainda não encerrados; nenhum contêiner próprio validado |
| Destino | Contexto em 0xfba18 e BLR 0xfbe14 ligam nominalmente 0x80080000+deslocamento_u32 | Não estabelece endereço efetivo desta Image no aparelho ou RAM livre |
| Propriedade | A própria Image inclui o registro; não precisa de outro buffer de saída | Região completa gravável/executável, reservas e ausência de concorrentes ainda não demonstradas |
| Coerência | [Helper LK](lk-cache-handoff.md): M=1 limpa M/C no EL atual; M=0/C=1 conserva C. Há chamadas depois | Cache da Image, outros agentes, traps e estado após callbacks não observados |
| Entrada | Diagnóstico aceita EL1/EL2 com M=C=0; [trecho final](lk-final-edges.md) delimitado | EL/SCTLR finais e permissões dos registradores de sistema não medidos |
| Argumentos e CPUs | Diagnóstico registra x0–x3/SP/MPIDR sem usar pilha/FDT; testes de uma CPU | x0 não é FDT certificado; exclusividade de uma CPU/região precisa de contrato |
| Aquisição | GDB recupera os bytes no QEMU, antes de reiniciar a VM | Não há canal demonstrado para ler a RAM do diagnóstico no Samsung |
| Vínculo e tempo | Leitor offline compara layout/endereço e, opcionalmente, Image inteira | Registro v1 não tem nonce/identificador de execução; autenticidade e frescor dependem do contexto de captura |
| Recuperação do aparelho | Há Android stock funcionando no último relato | Nenhum plano de retorno/retomada foi ensaiado para uma Image que estaciona em WFE |

O Marco B (R10 em uma CPU) continua exigindo também FDT/bancos/reservas
confiáveis e permissões GIC/timer. Resolver o Marco A não comprova esses dados.
O R10 exige EL2; a Image de diagnóstico aceita EL1/EL2. Os contratos são distintos.

## Percursos considerados

| Percurso | O que já se sabe | Estado nesta entrega |
|---|---|---|
| Boot stock + bugreport | Recuperou texto do bootloader via dumpstate | Observação stock; não executa a Image própria nem lê uma faixa arbitrária de RAM |
| Imagem Android própria via cadeia Samsung | Formato e trecho de cópia têm modelos; [instalador Proton](loader-contract.md) altera boot/vendor_boot | Não disponível como percurso demonstrado sob o último estado travado; nem pacote do diagnóstico nem aceitação/retorno validados |
| Chainload a partir de Linux | Shim antigo desativado; [referência pública](xfwdrev-kernel-reference.md) tem kexec e /dev/mem desativados | Não é um carregador existente; config de referência não prova config stock ou controle de EL2 |
| GDB QEMU | Carrega a Image bruta e lê registros/snapshot antes de continuar/resetar | Disponível somente no laboratório; não é conexão GDB do telefone |

Desbloqueio, root, recovery personalizado, protocolo Download e leitura de
memória não são presumidos disponíveis. Nenhuma transição, instalação, flash,
comando de dump OEM ou alteração de partição foi feita ou fornecida.

## Canais de recuperação

| Canal | Limite que impede tratá-lo como saída do diagnóstico |
|---|---|
| Bugreport/last_kmsg | Evidência de logs stock persistidos; não há ligação de transporte com os 128 bytes da Image própria |
| [Debug-snapshot LK](lk-memory-log.md) | Área 0xf0000000–0xf0210000 reservada para outro produtor. Não é memória livre nem há contrato para inserir o registro ali |
| [UART0/MUIC](uart-routing.md) | Roteamento/estado físico, clocks e acessibilidade ainda abertos. A Image atual não serializa o registro; habilitar uma UART sozinho não o transmite |
| Android depois de outro boot | Precisa provar retenção/reserva, endereço, leitura permitida e ausência de sobrescrita; não se presume que reset conserve a Image |
| HVC/log Harx | [Atributo negado](harx-log-observation.md); serviço de log não é leitura arbitrária do registro |
| Debugger/leitor de RAM externo ou OEM | Transporte, permissões, domínio de endereço e preservação ainda não identificados/demonstrados |

As coletas negadas não devem ser repetidas sem mudança concreta de acesso/canal.
Não copiar o registro para área reservada alheia, habilitar MMIO/SMC ou executar
consumidores NEWTIME fora do escopo para contornar essa lacuna.

## Contrato de uma futura captura

Antes de executar a Image no aparelho, registrar a rota que aceita o artefato
e o modo de recuperar a região **enquanto os bytes ainda pertencem ao ensaio**.
O contexto precisa incluir Image/ELF e hashes da mesma compilação, intervalo
completo, base efetiva, produtor da captura, instante/boot e operações ocorridas
entre entrada e leitura. O offset do registro vem do ELF correspondente.
Para o layout v1 atual, `diag_record = image_size - 128`; o QEMU confere essa
igualdade contra os símbolos do ELF. Uma alteração de layout exige revisão.

Adquirir 128 bytes exatos, sem prefixo de dump, e preferir também a Image inteira.
Conferir marcador/versão/tamanho, campos reservados, EL/M/C e base+offset.
Comparar a captura completa com a Image original, permitindo diferença só no
registro. Guardar originais privados fora do Git; não publicar cmdline, dumps,
seriais ou campos pessoais para provar origem.

Um registro sem marcador pode significar recusa, falta de execução, gravação
incompleta ou captura errada. Um marcador válido pode ser antigo ou fabricado.
A inspeção isolada não escolhe entre essas hipóteses, não autentica execução
e não comprova persistência. Não há antirreplay no formato v1.

## Leitor e ensaio disponíveis agora

`inspect_entry_record.py` lê somente arquivos locais, limita entradas e emite
JSON. Recusa tamanho diferente de 128, marcador incompleto, versão/layout ou
estado incompatíveis e endereços divergentes. `--snapshot` exige comparação
byte a byte da Image inteira. O resultado distingue `record_fields_only` de
`full_image_bytes`; origem, frescor e autenticação continuam `not_verified`.
O leitor nunca dereferencia x0 ou determina que a base declarada seja RAM livre.

Exemplo **somente QEMU**, com diretório novo:

```bash
python3 scripts/test_entry_diag.py --output-dir build/entry-captures-local
python3 scripts/inspect_entry_record.py \
  build/entry-captures-local/el1-offset0-mc0.record \
  --image build/entry-captures-local/entry_diag.Image \
  --load-address 0x40080000 \
  --snapshot build/entry-captures-local/el1-offset0-mc0.snapshot
python3 scripts/test_entry_record.py
python3 scripts/validate_baseline.py
```

O harness exporta referência, registros e snapshots de sucesso, mais
`captures.json` com fonte QEMU, endereços e hashes após completar os testes.
Recusas exportam os bytes sem marcador completo; o leitor os rejeita e não
as classifica por si só. Dezessete testes de host e seis registros reais do
QEMU passam; seis capturas sem marcador são recusadas. O baseline/CI
exige ambas as verificações. [Evidência](references/diagnostic-contract-20261026.json).

## Próxima investigação

O próximo passo é delimitar **uma interface concreta de carga e aquisição**,
com suas permissões e preservação, usando as imagens/fontes existentes.
Se uma rotina de dump/exportação for candidata, seguir seu despacho, faixas
e transporte estaticamente antes de atribuir leitura da Image a ela. Para a
rota Android própria, fechar aceitação/transformações ainda abertas no LK.
Sem uma interface disponível nas condições do aparelho, registrar o bloqueio
e a condição específica que mudaria a decisão; mais uma busca de constantes
ou leitura Shizuku já negada não o resolve. Nenhuma execução física é próxima
etapa automática desta matriz.
