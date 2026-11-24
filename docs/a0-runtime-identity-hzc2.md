# Como distinguir uma captura HZC2 de uma captura com o banner A0

O bugreport ZTO de 27/10 traz no cabeçalho do membro principal um campo
`Kernel:` com os mesmos 341 bytes de `linux_banner` da Image Samsung.
O protótipo B empacotado contém um banner de 318 bytes. A versão 5.4.242
é comum aos dois. O texto completo diferencia os dois artefatos medidos.

| Medição na Image (offsets relativos ao início do kernel) | Samsung HZC2 | Alinhado A0 no protótipo B |
|---|---|---|
| SHA-256 da Image | 28cb5598e8287da2e4fe238030d2b2f4dd96233f458a4bccf6d17688b6ad2bb0 | 9614f9a0ec8e83177ccb2010a585a128fd11f028cb46c417f2c1dbed2c2fd571 |
| Offset de linux_banner | 0x17a05e4 | 0x179b1e4 |
| SHA-256 do banner, incluindo LF e excluindo NUL | 021b80430696d9d788ba9e339f36783fe7def993ab8b89a326c74c88f0cafe2e | 7959587b8848e40ea2cf4b5168a198981b749ac4ee7a4c5e44093075e74a4835 |
| Intervalo [__start_notes, __stop_notes) | [0x198e3e8, 0x198e418) | [0x19883e8, 0x1988418) |
| GNU build ID do kernel nesse intervalo | a94ff1974ca947ec | 266590f721e1bfda |

Para reproduzir, partir do [boot Samsung fixado](references/capture-a0-pins-hzc2.json)
e do [arquivo B fixado](references/capture-a0-natural-b-artifact-20261104.json).
Conferir os hashes de boot.img, ler o comprimento little-endian no offset 8
do header v3 e tomar esse número de bytes a partir de 4096. Usar `decode`
e `boundaries` de scripts/capture_a0_kallsyms.py nas duas Images para
localizar os três símbolos da tabela. Em B, `readelf -n` no vmlinux alinhado
também retorna o ID de 8 bytes. As Images contêm outras notas GNU fora
desse intervalo, portanto escolher a primeira ocorrência de GNU dá outro ID.

O código Samsung kernel/ksysfs.c, linhas 188–205, descreve a leitura desse
intervalo por sysfs. O [ZIP de 27/10](bugreport-boot-hzc2.md) não contém
um arquivo sys/kernel/notes. Os dois IDs da tabela são medições dos artefatos.
O sinal disponível nesse bugreport é o banner.

## Comparar um bugreport já coletado

```sh
python3 scripts/inspect_a0_runtime.py /caminho/bugreport.zip
python3 scripts/test_a0_runtime.py
```

O leitor segue main_entry.txt e compara apenas o campo Kernel do cabeçalho
e a primeira coluna de uma seção LSMOD completa no mesmo membro. Nomes
citados exclusivamente como dependências ficam fora da lista. A saída
contém a referência do banner, hashes, contagem e quatro indicadores de
presença. Os formatos aceitos são os do dumpstate Samsung e os limites
de arquivo são os mesmos usados no leitor de boot de 27/10.

| Resultado | Interpretação |
|---|---|
| banner_match = samsung_hzc2 | O cabeçalho reproduz o banner da Image Samsung de referência. |
| banner_match = aligned_a0 | O cabeçalho reproduz o banner do candidato alinhado fixado. |
| banner_match = unknown | O texto difere das duas referências. |
| matches_stock_names = true | A lista de nomes distintos coincide com os 276 da captura ZTO. |

No ZIP real, o resultado é **samsung_hzc2**, com **276 nomes** e os quatro
módulos presentes. Ordenando os nomes em ASCII, um por linha com LF
inclusive na última, o SHA-256 é
`e914f326b924ddc338fc34649c990e69414f001b5c357278b0fd4d4de82f0df7`.
O controle com o banner extraído de B é sintético. Um banner pode ser
reutilizado por outro build e um relatório pode ser editado. O leitor
atribui correspondências textuais e de inventário. A execução física do
candidato continua pendente.
