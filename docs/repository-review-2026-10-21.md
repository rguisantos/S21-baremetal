# Revisão e organização — 2026-10-21 (UTC)

Base revisada: `b7185e43d05082bdcfdd363b759d1197e2bd0939`, main sincronizada com origin no início. Revisão do inventário versionado, documentação de entrada, scripts de reprodução, escopo das referências Samsung e dois READMEs anexados. Esta etapa não constitui nova auditoria linha a linha de todos os drivers nem execução no telefone.

## Resultado e organização

- Criado índice em [docs/README.md](README.md), catálogo em [scripts/README.md](../scripts/README.md) e identificação do recorte em [samsung_kernel/README.md](../samsung_kernel/README.md).
- Preservados caminhos dos fontes, ferramentas e histórico. Não reescrito o histórico Git nem removido o toolchain offline. No checkout desta revisão, tools/root ocupa aproximadamente 559 MiB e tools/debs 79 MiB.
- Identificados scripts antigos com caminhos absolutos e snapshot que descreve inclusão de `.env`; não pertencem ao fluxo validado atual e não foram executados.
- Corrigida a contagem atual do teste de contêiner para 60; o registro anterior de 59 correspondia à etapa anterior ao teste adicional de kernel_end relativo.
- Nenhum diagnóstico privado ou firmware bruto foi acrescentado ao Git. Temporários locais preexistentes do toolchain foram preservados.

## Arquivos extras: o que realmente falta

**Atualização posterior:** pacote BL HZC2 recebido, MD5 conferido e componentes analisados. A solicitação abaixo foi atendida; veja [bootloader-hzc2.md](bootloader-hzc2.md). Nenhum novo envio é necessário para continuar a análise estática.

| Prioridade | Arquivo/evidência | Motivo e limite |
|---|---|---|
| Próxima análise estática | **Pacote `BL_...G998BXXSJHZC2...tar.md5` do mesmo firmware stock**; nome exato conforme o pacote | Inventariar os componentes reais e procurar validação da Image, ajustes do DTB e salto final. Não presumir que exista abl.img ou outro nome específico. O BL não exige root para ser obtido do pacote firmware e não será instalado. |
| Alternativa ao BL inteiro | Lista de membros do BL, seguida dos binários de boot identificados e seus hashes | Permite solicitar apenas componentes relevantes; um `tar -tf` local é suficiente como inventário inicial. Não pedir arquivos inexistentes pelo nome. |
| Etapa futura de execução | FDT **final passado pelo bootloader**, com RAM e reservas, mais evidência de EL/cache/argumentos de entrada | O DTB estático não substitui isso. BL pode explicar a construção, mas sozinho não garante valores de execução. Ainda falta um canal de diagnóstico demonstrado. |
| Somente se houver nova reconstrução do kernel | Pacote-fonte completo/base exata e delta, caso não estejam mais disponíveis localmente | Já foram analisados; não são necessários para repetir os testes atuais ou organizar a documentação. |

**Não é necessário reenviar agora** README_Kernel.txt, README_Platform.txt, imagens stock já analisadas, ZIP Proton público, logs vazios ou a coleta Shizuku que retornou Permission denied. Não solicitar EFS, dados pessoais ou dumps completos de armazenamento. A prioridade de arquivo é BL HZC2; continuar testes de software não depende desse envio.

## Leitura dos anexos

README_Kernel.txt descreve `exynos2100-p3sxxx_defconfig`, GCC Android 4.9/Clang r383902, saídas Image/módulos e variáveis PLATFORM_VERSION=11/ANDROID_MAJOR_VERSION=r. README_Platform.txt indica Android 15.0 e integração de módulos no AOSP. Essa diferença é registrada como conteúdo dos documentos, não como prova de que o telefone execute Android 11. Nenhum fornece mapa de RAM, configuração UART ativa ou contrato de handoff. Hashes em [samsung-reference.md](samsung-reference.md).

## Verificação desta revisão

Nova execução: FDT **43/43**, contêiner **60/60** e materialização **17/17**, com ASan/UBSan; carregador QEMU **um handoff na main de produção e cinco recusas**, todos PASS. Regressão R8A/R8B/R8C/R9: **4/4 PASS**. Links locais da documentação: **74 conferidos, nenhum ausente**. Cobertura permanece software host/QEMU; não valida Exynos, SMP, USI, boot Samsung ou flash. O shim continua em quarentena. Para detalhes do ensaio com main real, ver [qemu-el2-loader.md](qemu-el2-loader.md).
