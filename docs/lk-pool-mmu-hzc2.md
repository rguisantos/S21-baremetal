# LK HZC2: construção da tradução e atributos do pool UFS

O [pool do heap UFS](lk-heap-pool-hzc2.md) agora está ligado ao construtor
de tabelas do LK. No perfil selecionado **EL1, granule herdado de4KiB**,
as 3043 páginas de `[0xe8c1d000,0xe9800000)` recebem tradução de estágio1
por identidade e atributos de memória normal cacheável. O código original
produziu as tabelas previstas em QEMU; cada página do pool foi conferida
por leitura dos descritores gerados.

Isso fecha a construção nominal da tradução da CPU nesse perfil. Não é
uma captura das tabelas do telefone nem demonstra a tradução de barramento,
SMMU, IOCC ou coerência DMA. O pool continua pertencendo ao LK.

Análise de 30/10/2026, Campo Grande, base main `c7aa567`, após PR #69.
Sboot HZC2:4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo; delta nominal VA−arquivo `0xe7f14000`.

## Registro, construtor e ordem selecionada

O registro de40 bytes em `0x31fdc8` contém:

| Campo | Valor |
|---|---|
| VA inicial | `0xe8000000` |
| Argumento de fim | `0xe9800000` |
| PA inicial fornecido | `0xe8000000` |
| Flags | `0x0020000000000745` |
| Nome | `LK` |

A rotina `0x18a1f0` percorre11 registros desde `0x31fd28`, com passo40,
e chama `0x189f68` com os quatro primeiros campos. Alguns outros registros
usam valores não alinhados como argumento de fim; eles são conservados
como valores brutos, sem impor uma convenção universal de fim inclusivo.
O registro LK tem ambos os limites alinhados a2MiB.

A cadeia selecionada é `0xfa9a0 → 0xee660 → 0xee738 → 0x18a390 →
0x18a1f0`. No mesmo trecho de startup, o heap é inicializado depois, em
`0xfa9c8`. Chamadas anteriores e preservação continuam condicionais.
O construtor, a instalação e os setters de M/C/I foram separados; a ordem
estática não foi promovida a estado vivo observado.

## O que os descritores representam

O mapper usa blocos de2MiB fora da janela LK e páginas de4KiB dentro dela.
No ramo de páginas, monta a base do descritor a partir do VA corrente.
Isso torna esse ramo nominalmente identidade, inclusive no controle de
laboratório que muda o argumento PA. O chamador real fornece VA=PA no
registro LK; o controle alterado não é uma observação do aparelho.

| Estrutura/campo | Valor solicitado ou produzido |
|---|---|
| Raiz L1, TTBR0/TTBR1 | relativo `0x322000` |
| Tabelas L2 | relativo `0x323000`, 48 links iniciais |
| Tabelas L3 da janela LK | relativo `0x353000`, índice por bloco |
| MAIR_EL1 | `0xff44` |
| TCR_EL1 | `0x11b51c351c`: T0SZ28, TG0=0 (4KiB), IPS1 (36 bits) |
| AttrIndx do pool | 1 → byte MAIR `0xff`, memória normal write-back |
| SH / AF / AP | 3 (inner-shareable) / 1 / `01` |
| Acesso EL1 ao pool | Leitura/escrita, PXN1 |

PXN1 impede execução privilegiada nesse descritor; UXN permanece0. O
modelo conserva os bits brutos e não chama o pool genericamente de
“não executável” em todos os níveis de privilégio.

Há tratamento distinto para o intervalo anterior ao marcador relativo
`0x20d000` e para as páginas das tabelas `[0x322000,0x363000)`: o primeiro
recebe leitura apenas e PXN0; o segundo, leitura apenas e PXN1. O pool
fica fora desses intervalos e mantém os atributos de escrita do registro.

As definições de bits e a interpretação dos bytes MAIR foram cruzadas
com três fontes fixadas do FlopKernel:
[`pgtable-hwdef.h`](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/arch/arm64/include/asm/pgtable-hwdef.h),
[`memory.h`](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/arch/arm64/include/asm/memory.h) e
[`proc.S`](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/arch/arm64/mm/proc.S).
O índice Linux para MT_NORMAL é diferente: aqui a interpretação vem do
byte `0xff` no MAIR pedido pelo LK. [Manifesto por blob/SHA-256](references/flop-mmu-source-reference.json).

## Condição que permanece explícita

O helper `0x189e50` lê TG0 do TCR herdado para fornecer o tamanho de página
**antes** de `0x18a168` instalar o novo TCR. Portanto, a constante nova de
4KiB não prova sozinha que o construtor já recebeu4KiB. A análise e o
ensaio escolhem explicitamente EL1/4096. Outros granules não foram
certificados, e o TCR herdado do telefone não foi adquirido.

A tabela de três atualizações posteriores em `0x31fcb0` contém faixas
altas entre `0x880000000` e `0x89e000000`, sem atingir o pool nominal.
Isso delimita essas três entradas; não inventaria todos os escritores
ou aliases de tabelas durante a execução.

## Ensaio original e verificação

`emulate_lk_pool_mmu_qemu.py` executa o fragmento original que zera a raiz
e publica seus48 links, e o corpo original do mapper. Fornece EL1 e4096
nos dois helpers de consulta. L2/L3 começam zeradas; o ensaio não executa
o startup Samsung, instalação de TTBR/TCR/MAIR ou ativação da MMU.
Nenhuma tabela gerada é instalada na VM.

São seis casos de mapeamento, em duas posições do código:

- Registro LK, relocado apenas para a RAM de laboratório: a imagem de
  tabelas coincide byte a byte com o modelo e todas as3043 páginas do
  pool têm saída igual ao VA e os mesmos atributos.
- Mesmo intervalo, com PA fornecido alterado: o ramo LK continua a gerar
  os mesmos descritores por VA; é um controle sintético da interpretação.
- Fora do LK, VA`0x80001234` recebe saída`0x90001234` por bloco L2. Esse
  controle confirma que a leitura de tabelas distingue tradução não identidade.

Guardas, ABI e segmentos de código originais foram conservados. Há ainda
21 testes de host para geometria, permissões, recusas de descritores,
limites de36 bits, tabelas truncadas e mutações dos argumentos.
O extrator confere292 palavras GNU,66 destinos,99 operandos,14 registros
de mapeamento/atualização e12 grafos. Os relatórios estático e QEMU foram
reproduzidos byte a byte.

```sh
python3 scripts/test_lk_pool_mmu.py -v
python3 scripts/inspect_lk_pool_mmu.py /private/path/sboot.bin > /tmp/pool-mmu.json
cmp /tmp/pool-mmu.json docs/references/lk-pool-mmu-hzc2.json
python3 scripts/emulate_lk_pool_mmu_qemu.py /private/path/sboot.bin > /tmp/pool-mmu-qemu.json
cmp /tmp/pool-mmu-qemu.json docs/references/lk-pool-mmu-qemu-hzc2.json
python3 scripts/validate_baseline.py --output-dir build/baseline-lk-pool-mmu
```

[Relatório estático](references/lk-pool-mmu-hzc2.json),
[ensaio QEMU](references/lk-pool-mmu-qemu-hzc2.json) e
[validação](references/lk-pool-mmu-validation-20261030.json) conservam as
evidências. Próximo: origem do granule herdado e caminho de coerência/DMA,
além do produtor da configuração `0xcd31c8` e gates RPMB. A construção
nominal de identidade não substitui os contratos físicos do diagnóstico.

Continuação de31/10/2026: a [entrada e o getter TG0 originais](lk-entry-granule-hzc2.md) foram executados em QEMU. EL2h→EL1h conserva o TCR fornecido; EL1t é preservado. O censo encontra restauração de contexto e writer posterior, sem fornecer o granule inicial do telefone.
