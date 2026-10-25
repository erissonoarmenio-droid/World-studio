# Mapa de capacidades: sistema do estúdio W-orld (fase 0 da especificação)

Versão 1.0 — 25/out/2026. **Mapa aprovado por Eri (11h50)**: contas GitHub e Cloudflare ok; vídeo no servidor pela Atlas ok; palavra-senha ajustada. v0.2: piloto + cadastro. Método: skill `spec-driven-development` (fase 0). **Aprovado em 25/10.** Próximo: especificação do `nucleo` (`aios/projects/spec-nucleo.md`).
Base: `aios/projects/plano-construcao.md` (§1–7), `claude/arquitetura-estudio-ugc.md`, `claude/atendente.md` v2.5, `aios/projects/processos-social-media.md`, `aios/projects/processos-criativos.md`, `aios/projects/comparativo-apis.md` (§7–8), protótipo "Central W-orld".

## Por que dividir em módulos
O pedido junta várias capacidades que podem ser testadas e entregues separadamente (conversa, geração, créditos, Instagram, Central, pagamento). Uma especificação única ficaria grande demais para revisar. Cada módulo abaixo ganha a sua especificação curta, na ordem de construção.

## Módulos

| Id | O que faz | Depende de |
|---|---|---|
| `nucleo` | Servidor, banco de dados, cadastro das lojas, guarda segura das chaves, armazenamento de fotos e vídeos, fila de trabalhos, registro de eventos e de custos, backup diário | — |
| `creditos` | Planos, saldo de créditos, débito e estorno por geração, validade (mês / 90 dias), situação da loja (ativa, vencendo, pausada, cancelada) e o liga/desliga | `nucleo` |
| `geracao` | Trabalhador que gera: foto (Google), vídeo (Seedance), voz (MiniMax), arte (desenho por código), story animado (Remotion); máscara e trava de cenário; custo real de cada trabalho; só roda com crédito e aprovação | `nucleo`, `creditos` |
| `qualidade` | Verificador de fidelidade depois de gerar, registro de erros e Analista de Erros diário (23h), que só propõe regras | `geracao` |
| `conversa` | Bot do Telegram com a influencer (Atendente no Sonnet): primeiro contato, criação da influencer e da voz, catálogo por código, pedidos de foto e vídeo, custo e ok, entrega, áudios, passar para o Eri | `nucleo`, `creditos`, `geracao` |
| `central` | Web app só do Eri (login): painel, galeria, calendário, conversas e "assumir", lojas, planos e créditos (ligar/desligar, liberar créditos na mão), vendas, sistema, erros, aprovações, aprendizado, configurações, pausar tudo | `nucleo`, `creditos`, `conversa`, `qualidade` |
| `instagram` | Conectar e desconectar o Instagram da loja por link, publicar com rótulo de IA, ler métricas e comentários | `nucleo`, `creditos` |
| `social-media` | Processos do plano Social Media: monitoramento, plano do mês e calendário, produção na véspera, lembrete e publicação, relacionamento, relatório mensal (tarefas agendadas) | `conversa`, `geracao`, `instagram` |
| `pagamento` | Link de pagamento e aviso automático de pagamento que libera plano e créditos. **Pronto, mas desligado no piloto** (sem CNPJ: liberação na mão pela Central) | `creditos` |

Sem ciclos: as setas só apontam para módulos de cima. A conversa pede gerações e débitos; nada lá embaixo chama a conversa de volta, só avisa por eventos na fila.

## Ordem de construção (piloto com 1 loja)
1. `nucleo`
2. `creditos`
3. `geracao` (primeiro só foto)
4. `conversa` (primeiro contato + criação da influencer + pedido de foto)
5. `central` v1 (leitura + aprovações + ligar/desligar + liberar créditos)
6. `geracao` (vídeo + voz) e `qualidade`
7. `instagram`
8. `social-media`
9. `pagamento` (por último, desligado)

**Primeira entrega útil (fim do passo 5):** a loja do piloto conversa com a influencer no Telegram, cria a influencer, pede uma foto, vê o custo, aprova, recebe a foto; Eri acompanha e aprova tudo pela Central.

## Suposições que estou fazendo (corrija agora, ou sigo com elas)
1. **Linguagem e base:** Python 3.12 + FastAPI, porque todo o código que já temos é Python (`gerar_foto_google.py`, `trava_cenario.py`, `mascara_peca.py`, `erros.py`, `referencias.py`).
2. **Banco:** PostgreSQL no próprio Railway.
3. **Fila de trabalhos:** uma tabela no próprio Postgres (sem Redis) no piloto, para ficar simples e barato.
4. **Fotos e vídeos:** Cloudflare R2 (10 GB grátis), que também guarda o backup diário do banco fora do Railway. **Precisa de uma conta Cloudflare do Eri.**
5. **Código:** repositório privado no GitHub do Eri, que o Railway publica sozinho a cada mudança. **Precisa de uma conta GitHub do Eri.**
6. **Central:** páginas servidas pelo mesmo servidor, com o visual do protótipo (acrílico Frutiger Aero), instalável no celular (PWA). Login só do Eri: senha + código do celular (2 fatores).
7. **Telegram:** um bot só, por webhook, para todas as lojas.
8. **Vídeo no servidor: Atlas Cloud como principal**, não o Higgsfield. Motivo: no servidor precisamos de uma API documentada, e a do Seedance no Higgsfield não é (`comparativo-apis.md` §1); a Atlas já funcionou em 24–25/10 com o rosto da influencer e com a voz de referência. Custo maior (~US$ 0,32 para 4 s, ~US$ 0,49 para 6 s contra ~US$ 0,29 no Higgsfield). O Higgsfield segue nos testes manuais até confirmar a API dele.
9. **Fotos:** Google direto (`gemini-nano-banana-2.1`), decisão de 24/10. **Voz:** MiniMax SweetGirl 1,25× feliz, decisão de 25/10. **Cérebro:** Claude Sonnet 5.5 na conversa.
10. **Fase de teste:** toda geração passa pela fila de aprovação do Eri na Central, além do ok da lojista (regra "meu ok obrigatório", que pode ser desligada depois).
11. **Piloto:** 1 loja, com o plano e os créditos liberados na mão; as regras de créditos valem desde já, para medir o custo real.

## Perguntas em aberto
- ~~Qual loja e qual plano~~ → **plano completo (Social Media) para a loja de teste**; nome da loja ainda não definido (Eri, 25/10, 11h44).
- Tudo bem criar as contas **GitHub** e **Cloudflare** (as duas grátis) na hora de começar o `nucleo`?
- Vídeo pela **Atlas** no servidor (suposição 8) está ok, mesmo custando um pouco mais?

## Cadastro da loja (pedido de Eri, 25/10, 11h44) — proposta para aprovar
Cada loja tem um cadastro que a influencer monta **conversando** (sem formulário), guardado no `nucleo` e visto e editado por Eri na Central (ficha da loja). Regra de ouro (LGPD): **pedir só o que é usado, na hora em que passa a ser preciso.**

**1. Quem é a pessoa (no primeiro contato)**
- nome; papel (dona, sócia, funcionária); WhatsApp; e-mail (para recibo e avisos importantes);
- conta do Telegram (automático: é o "login" da pessoa no bot).

**2. A loja (no primeiro contato, a maior parte tirada do Instagram e só confirmada)**
- nome da loja; @ do Instagram; o que vende; cidade/UF; onde vende (Instagram, WhatsApp, site, loja física); horário; endereço da loja física (opcional, para responder clientes).

**3. Dados fiscais (só quando for pagar ou assinar contrato — não no piloto)**
- CNPJ (ou CPF, se ainda não tiver empresa) e razão social; validados pelo dígito e pela consulta pública do CNPJ (ex.: BrasilAPI), para conferir nome e situação ativa;
- endereço de cobrança, se o meio de pagamento exigir.

**4. Marca e influencer (ao longo das conversas)** — já previstos no `atendente.md`: tom, cliente-alvo e biótipo, kit da marca, influencers de referência, nome, aparência e voz da influencer, catálogo por código, base de respostas (preço, tamanhos, frete, pagamento, troca, horário).

**5. Permissões e consentimentos (cada um com data, hora e versão do texto)**
- **aceite dos termos de uso e privacidade** — obrigatório antes da primeira geração;
- uso dos dados de forma agregada para melhorar o serviço (decisão de 24/10);
- conexão do Instagram e o que ela pode fazer lá (publicar, responder, ler métricas);
- envio pelo WhatsApp em nome da loja (se ligar);
- ordens fixas ("pode responder sozinha perguntas de horário");
- consentimento do clone de rosto/voz (só se a pessoa quiser ser a influencer).

**6. Pessoas autorizadas e papéis**
- **Dona (titular):** tudo — aprovar gastos, plano, pagamento, Instagram, convidar pessoas, apagar dados.
- **Funcionária:** pedir fotos e vídeos, cadastrar peças, ver calendário. Aprovar gastos **só se a dona liberar** (com limite por mês, opcional). Nunca: pagamento, apagar dados, desconectar Instagram.
- Como entra: a dona pede um **código de convite** à influencer e passa para a funcionária, que manda o código no bot.

**7. Plano e situação** (módulo `creditos`): plano, créditos, validade, situação, histórico de pagamentos.

**Na Central:** ficha completa da loja, editar, ver o histórico de consentimentos, **exportar** e **apagar** os dados da loja a pedido (LGPD).

**8. Palavra-senha para aprovar gastos (ideia de Eri, 25/10, 11h47) — proposta**
- **A dona** cria a palavra-senha na conversa (só ela compra créditos, mexe no plano e liga o modo automático). A funcionária não tem palavra-senha; aprovar os gastos do dia a dia ("sim"/"não") ela só pode se a dona liberar (item 6).
- **Guardada embaralhada** (hash): nem o Eri nem o sistema conseguem ler; a influencer nunca repete a palavra.
- Ao digitar, **o bot apaga a mensagem** com a palavra na hora (o Telegram permite ao bot apagar mensagens recebidas no chat privado), para ela não ficar no histórico do celular.
- **Quando pede (correção de Eri, 11h50):** **só** para (1) comprar créditos extras, (2) mudar ou cancelar o plano e (3) ligar o **modo automático**. A produção do dia a dia **não pede senha**: a pessoa só aprova ou recusa cada gasto ("sim" / "não"), como já está no `atendente.md`. Depois de digitada, vale 30 minutos.
- **Modo automático:** ordem fixa em que ela produz sozinha dentro de um limite de créditos por semana ou mês, sem pedir ok a cada post. Só liga com a palavra-senha da dona, com o limite dito na hora, e desliga com uma frase ("desliga o automático"), sem senha. A especificar no módulo `social-media`.
- **Errou 5 vezes:** aprovações bloqueadas por 15 minutos, aviso à dona e à Central.
- **Esqueceu:** a pessoa diz "esqueci" → a influencer manda um **código de 6 números** para o e-mail ou WhatsApp cadastrado dela → a pessoa digita o código no bot → cria uma palavra nova. Sem acesso ao e-mail nem ao WhatsApp: passa para o Eri, que confirma quem é e libera a troca pela Central. Opcional: uma **dica** que a própria pessoa escreve ao criar ("nome do meu primeiro cachorro").
