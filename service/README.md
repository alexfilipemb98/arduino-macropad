# MacroPad Service

Serviço em Python para integrar o MacroPad Arduino com ações no Windows (atalhos de teclado, escrita de texto/snippets, abertura de aplicações e controlo de LEDs RGB), a correr em segundo plano com ícone na bandeja do sistema (system tray).

## Funcionalidades

- **Comunicação Serial Bidirecional**: deteção e ligação com o Arduino através de porta COM configurável.
- **Sincronização de Relógio**: envio periódico da data/hora atual para apresentação no ecrã OLED do MacroPad.
- **Execução de Macros**: processamento de eventos `TECLA:x` enviados pelo dispositivo.
- **Simulação Segura de Teclado**: suporte para caracteres especiais e acentuação no Windows (`SendInput` com suporte para layout de teclado e fallback Unicode).
- **Interface de Configuração (`Tkinter`)**: seleção gráfica da porta COM e da taxa de transmissão (*baud rate*).
- **Execução em Segundo Plano (`pystray`)**: ícone na system tray para pausar/retomar serviço, abrir configurações ou encerrar.
- **Controlo de LEDs NeoPixel**: alternância e sincronização de estados de iluminação RGB.

## Pré-requisitos

- Windows 10 / 11
- Python 3.10+
- Dispositivo Arduino com o firmware carregado (`arduino/arduino.ino`)

## Instalação

No diretório do projeto ou da pasta `service/`, instalar as dependências necessárias:

```powershell
py -m pip install pyserial pyautogui pystray pyperclip pillow
```

## Configuração

O serviço utiliza o ficheiro `user.dat` para persistir a porta COM e o baud rate selecionados.
- Um modelo de exemplo é disponibilizado em `user.dat.example`.
- O ficheiro `user.dat` é criado automaticamente após guardar as configurações pela primeira vez na interface gráfica.
- **Nota**: O ficheiro `user.dat` é ignorado pelo Git (`.gitignore`) para que as configurações da sua máquina não sejam enviadas para o repositório público.

## Como Executar

Para iniciar o serviço em modo de desenvolvimento:

```powershell
py service.py
```

Ao iniciar:
1. O serviço tenta carregar as definições de `user.dat` (ou `user.dat.example` como fallback) e conectar-se ao Arduino.
2. É criado um ícone na bandeja do sistema (junto ao relógio do Windows) com as opções:
   - **Configurações**: abre a janela para selecionar a porta COM e baud rate.
   - **Iniciar / Parar Serviço**: permite pausar temporariamente a leitura da porta serial.
   - **Sair**: fecha a porta COM e encerra a aplicação.

## Build para Executável (.exe)

Para criar um ficheiro `.exe` autónomo (que não necessita de consola aberta):

1. Instalar o PyInstaller:
   ```powershell
   py -m pip install pyinstaller
   ```
2. Executar o script de compilação:
   ```powershell
   deploy.bat
   ```
   Ou manualmente:
   ```powershell
   py -m PyInstaller --noconsole --onefile --name "MacroPadService" service.py
   ```
3. O executável será gerado na pasta `dist/MacroPadService.exe`.

## Mapeamento de Teclas Demo

O código em `service.py` inclui um conjunto de macros de demonstração pré-configuradas:

| Tecla | Ação Executada | Mensagem no Ecrã OLED | Descrição / Demonstração |
| :---: | :--- | :--- | :--- |
| **0** | `Print Screen` | `Print Screen` | Captura de ecrã nativa do Windows |
| **1** | Escreve clipboard | `Escrever` / `Clipboard vazio` | Digita o texto atualmente copiado |
| **2** | Digita texto demo | `Demo Texto` | Exemplo de snippet / digitação de texto |
| **3** | Pisca LED + Texto | `Demo 3` | Ativação temporária de NeoPixel + digitação |
| **4** | Executa Bloco de Notas | `Bloco Notas` | Exemplo de abertura de aplicação (`notepad.exe`) |
| **5** | Digita email demo | `Demo Email` | Exemplo de digitação de email / modelo |
| **6** | Alterna LED 1 | `Spotify` / `Spotify OFF` | Toggle de estado com LED Verde (ex: multimédia) |
| **7** | Alterna LED 2 | `Discord` / `Desligado` | Toggle de estado com LED Azul (ex: mute de app) |
| **8** | Silenciar áudio | `Audio Mute` | Envia tecla `volumemute` do Windows |
| **9** | Executa Calculadora | `Calculadora` | Exemplo de abertura de ferramenta (`calc.exe`) |

## Personalização e Segurança

> [!WARNING]
> **Boas Práticas de Segurança em Repositórios Públicos**:
> - **Nunca guarde palavras-passe ou credenciais privadas diretamente no código-fonte.**
> - Para macros que necessitem de autenticação ou tokens pessoais, utilize variáveis de ambiente (`os.getenv("MINHA_VAR")`) ou um ficheiro local não versionado (ex: `.env` ou ficheiro JSON listado no `.gitignore`).
> - Ao personalizar os caminhos de ficheiros (como executáveis ou pastas de trabalho), verifique se os mesmos não contêm nomes de utilizador ou caminhos sensíveis da sua máquina antes de publicar alterações.
