# Guia de Instalação: Multi-Agent (Por Usuário)

Como o Windows não permite que processos iniciados por um usuário interajam na área de trabalho de outro usuário, o **Manager RPA** utiliza a arquitetura Multi-Agent. 

Nesta configuração, uma instância minúscula e invisível do **Agent** será executada no fundo para **cada perfil** do Windows assim que a pessoa fizer login.

## Passo a Passo para Inicialização Automática

Repita os passos abaixo para **cada usuário** (ex: `user1`, `user2`, `user3`) que roda robôs RPA no servidor:

### 1. Fazer o Login no Perfil do Usuário
- Faça o acesso remoto (RDP) ou logue no Windows com a conta desejada (ex: entre com o `user1`).

### 2. Abrir a Pasta de Inicialização
- No teclado, aperte os botões `Windows + R` para abrir a janela "Executar".
- Digite exatamente: `shell:startup` e aperte **OK**.
- Uma pasta do Windows Explorer abrirá. Qualquer programa colocado aí iniciará junto com este usuário.

### 3. Criar o Arquivo Executável do Agent
- Dentro dessa pasta aberta (`shell:startup`), clique com o botão direito em qualquer espaço vazio.
- Vá em **Novo** -> **Documento de Texto**.
- Renomeie o arquivo inteiro (incluindo a extensão `.txt`) para: `iniciar_agent.bat`
- O Windows perguntará se você tem certeza que deseja alterar a extensão. Clique em **Sim**.

### 4. Configurar o Arquivo
- Clique com o botão direito no arquivo `iniciar_agent.bat` e escolha **Editar**.
- Cole o seguinte código dentro dele (ajuste o caminho se a pasta `Manager RPA` estiver em outro local):

```bat
@echo off
:: Navega para a pasta raiz do Agent do Manager RPA
cd "C:\Users\juano\OneDrive\Desktop\Manager RPA\Agent"

:: Inicia o python de forma totalmente invisível (pythonw não abre tela preta)
start /B pythonw main.py
```

- Salve o arquivo (Arquivo > Salvar, ou `Ctrl + S`) e feche o bloco de notas.

---

## Como sei se deu certo?

1. Para testar sem precisar reiniciar o computador, basta dar **dois cliques rápidos** no `iniciar_agent.bat`.
2. Absolutamente **nada** aparecerá na tela do usuário (o processo é 100% invisível por causa do uso do `pythonw`).
3. Vá até a tela do **Orquestrador**. 
4. Você deverá ver, em no máximo 10 segundos, o card do servidor aparecer com o nome do usuário. Exemplo: `servidor-01-user1`.

Pronto! Repita isso logando no perfil do `user2` e do `user3`, e todos os robôs ficarão 100% mapeados e sob o controle do seu Painel Central.
