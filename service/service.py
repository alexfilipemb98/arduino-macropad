import serial
import serial.tools.list_ports
import pyautogui
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox
import pystray
import pyperclip 
from PIL import Image, ImageDraw
import sys
import os
import subprocess
import ctypes
import json
from ctypes import wintypes

# --- VARIÁVEIS GLOBAIS ---
arduino = None
a_correr = False
thread_serial = None
porta_atual = "COM3"
baud_atual = 9600
servico_estado = "parado"  # parado | a_iniciar | ativo
icone = None

INTERVALO_ENVIO_HORA = 1

def obter_caminho_configuracao():
    if getattr(sys, "frozen", False):
        diretorio_aplicacao = os.path.dirname(sys.executable)
    else:
        diretorio_aplicacao = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(diretorio_aplicacao, "user.dat")

def carregar_configuracoes():
    global porta_atual, baud_atual

    caminho_configuracao = obter_caminho_configuracao()
    if not os.path.exists(caminho_configuracao):
        # Fallback para user.dat.example se existir
        exemplo = caminho_configuracao + ".example"
        if os.path.exists(exemplo):
            try:
                with open(exemplo, "r", encoding="utf-8") as ficheiro:
                    configuracoes = json.load(ficheiro)
                porta_guardada = configuracoes.get("porta")
                baud_guardado = configuracoes.get("baud")
                if isinstance(porta_guardada, str) and porta_guardada:
                    porta_atual = porta_guardada
                if isinstance(baud_guardado, int) and baud_guardado > 0:
                    baud_atual = baud_guardado
            except (OSError, ValueError, TypeError) as erro:
                print(f"Não foi possível carregar exemplo de configurações: {erro}")
        return

    try:
        with open(caminho_configuracao, "r", encoding="utf-8") as ficheiro:
            configuracoes = json.load(ficheiro)

        porta_guardada = configuracoes.get("porta")
        baud_guardado = configuracoes.get("baud")

        if isinstance(porta_guardada, str) and porta_guardada:
            porta_atual = porta_guardada
        if isinstance(baud_guardado, int) and baud_guardado > 0:
            baud_atual = baud_guardado
    except (OSError, ValueError, TypeError) as erro:
        print(f"Não foi possível carregar as configurações: {erro}")

def guardar_configuracoes():
    caminho_configuracao = obter_caminho_configuracao()
    configuracoes = {
        "porta": porta_atual,
        "baud": baud_atual
    }

    with open(caminho_configuracao, "w", encoding="utf-8") as ficheiro:
        json.dump(configuracoes, ficheiro, ensure_ascii=False, indent=2)

# Guarda o estado dos LEDs para ligar/desligar
estado_pixels = {
    0: False,
    1: False,
    2: False
}

# --- FUNÇÕES DE COMUNICAÇÃO COM O ARDUINO ---
def enviar_comando(comando):
    """Envia um texto formatado para o Arduino"""
    global arduino
    if arduino and arduino.is_open:
        try:
            comando_formatado = f"{comando}\n".encode('utf-8')
            arduino.write(comando_formatado)
            arduino.flush()
        except Exception as e:
            print(f"Erro ao enviar: {e}")

def controlar_pixel(id_pixel, r, g, b):
    """Envia as cores para o LED específico no Arduino"""
    enviar_comando(f"PIXEL:{id_pixel},{r},{g},{b}")

def escrever_texto_seguro(texto):
    """Simula teclado no Windows respeitando o layout atual (inclui AltGr)."""
    ULONG_PTR = wintypes.WPARAM

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class INPUT_I(ctypes.Union):
        _fields_ = [
            ("mi", MOUSEINPUT),
            ("ki", KEYBDINPUT),
            ("hi", HARDWAREINPUT),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", wintypes.DWORD),
            ("ii", INPUT_I),
        ]

    INPUT_KEYBOARD = 1
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002
    VK_SHIFT = 0x10
    VK_CONTROL = 0x11
    VK_MENU = 0x12  # Alt

    SendInput = ctypes.windll.user32.SendInput
    SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    SendInput.restype = wintypes.UINT
    VkKeyScanExW = ctypes.windll.user32.VkKeyScanExW
    VkKeyScanExW.argtypes = (wintypes.WCHAR, wintypes.HKL)
    VkKeyScanExW.restype = ctypes.c_short
    LoadKeyboardLayoutW = ctypes.windll.user32.LoadKeyboardLayoutW
    LoadKeyboardLayoutW.argtypes = (wintypes.LPCWSTR, wintypes.UINT)
    LoadKeyboardLayoutW.restype = wintypes.HKL
    GetKeyboardLayout = ctypes.windll.user32.GetKeyboardLayout
    GetKeyboardLayout.argtypes = (wintypes.DWORD,)
    GetKeyboardLayout.restype = wintypes.HKL

    KLF_NOTELLSHELL = 0x00000080
    hkl_pt = LoadKeyboardLayoutW("00000816", KLF_NOTELLSHELL)
    hkl_ativo = GetKeyboardLayout(0)
    hkl_usar = hkl_pt if hkl_pt else hkl_ativo

    def enviar_input(inp):
        enviados = SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        if enviados == 0:
            raise ctypes.WinError()

    def tecla_vk(vk, keyup=False):
        flags = KEYEVENTF_KEYUP if keyup else 0
        inp = INPUT(
            type=INPUT_KEYBOARD,
            ii=INPUT_I(ki=KEYBDINPUT(vk, 0, flags, 0, 0)),
        )
        enviar_input(inp)

    def press_modificadores(shift, ctrl, alt):
        if shift:
            tecla_vk(VK_SHIFT, keyup=False)
        if ctrl:
            tecla_vk(VK_CONTROL, keyup=False)
        if alt:
            tecla_vk(VK_MENU, keyup=False)

    def release_modificadores(shift, ctrl, alt):
        if alt:
            tecla_vk(VK_MENU, keyup=True)
        if ctrl:
            tecla_vk(VK_CONTROL, keyup=True)
        if shift:
            tecla_vk(VK_SHIFT, keyup=True)

    def tecla_unicode(caractere):
        codigo = ord(caractere)
        key_down = INPUT(
            type=INPUT_KEYBOARD,
            ii=INPUT_I(ki=KEYBDINPUT(0, codigo, KEYEVENTF_UNICODE, 0, 0)),
        )
        key_up = INPUT(
            type=INPUT_KEYBOARD,
            ii=INPUT_I(ki=KEYBDINPUT(0, codigo, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)),
        )
        enviar_input(key_down)
        enviar_input(key_up)

    try:
        for caractere in texto:
            vk_pack = VkKeyScanExW(caractere, hkl_usar)
            if vk_pack == -1:
                tecla_unicode(caractere)
                continue

            vk = vk_pack & 0xFF
            shift_state = (vk_pack >> 8) & 0xFF
            usa_shift = bool(shift_state & 0x01)
            usa_ctrl = bool(shift_state & 0x02)
            usa_alt = bool(shift_state & 0x04)

            press_modificadores(usa_shift, usa_ctrl, usa_alt)
            tecla_vk(vk, keyup=False)
            tecla_vk(vk, keyup=True)
            release_modificadores(usa_shift, usa_ctrl, usa_alt)
            time.sleep(0.005)
    except Exception as e:
        print(f"Simulação de teclado falhou ({e}), fallback para pyautogui.write")
        pyautogui.write(texto, interval=0.01)

# --- NÚCLEO DO SERVIÇO (O QUE RODA EM SEGUNDO PLANO) ---
def atualizar_menu():
    if icone:
        icone.update_menu()

def definir_estado(novo_estado):
    global servico_estado
    servico_estado = novo_estado
    atualizar_menu()

def ouvir_arduino():
    global arduino, a_correr, porta_atual, baud_atual, estado_pixels
    
    ultimo_envio_hora = 0
    
    try:
        arduino = serial.Serial(porta_atual, baud_atual, timeout=0.1)
        time.sleep(2) # Dá tempo ao Arduino para acordar
        a_correr = True
        definir_estado("ativo")
        print(f"Ligado ao Arduino na porta {porta_atual}")
        ultimo_envio_hora = time.time() - INTERVALO_ENVIO_HORA
    except Exception as e:
        print(f"Erro ao ligar à porta {porta_atual}: {e}")
        a_correr = False
        definir_estado("parado")
        return # Sai da thread se falhar a ligação

    while a_correr:
        tempo_atual = time.time()
        
        # 1. ENVIAR A HORA PERIODICAMENTE
        if tempo_atual - ultimo_envio_hora > INTERVALO_ENVIO_HORA:
            hora_agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            enviar_comando(f"HORA:{hora_agora}")
            ultimo_envio_hora = tempo_atual
            
        # 2. OUVIR O ARDUINO E EXECUTAR MACROS
        try:
            if arduino.in_waiting > 0:
                linha = arduino.readline().decode('utf-8').strip()
                
                if linha.startswith("TECLA:"):
                    tecla = linha.split(":")[1]
                    
                    # === LÓGICA DA TECLA 0 ===
                    if tecla == '0':
                        pyautogui.press('printscreen')
                        enviar_comando("MSG:Print Screen")

                    # === LÓGICA DA TECLA 1 ===
                    elif tecla == '1':
                        texto = pyperclip.paste()
                        if texto:
                            escrever_texto_seguro(texto)
                            enviar_comando("MSG:Escrever")
                        else:
                            enviar_comando("MSG:Clipboard vazio")

                    # === LÓGICA DA TECLA 2 ===
                    elif tecla == '2':
                        # Demo: digitação de texto pré-configurado
                        escrever_texto_seguro("Hello from Arduino MacroPad!")
                        enviar_comando("MSG:Demo Texto")

                    # === LÓGICA DA TECLA 3 ===
                    elif tecla == '3':
                        # Demo: feedback visual com LED e digitação de texto
                        controlar_pixel(2, 100, 20, 60)
                        escrever_texto_seguro("MacroPad Demo 3")
                        enviar_comando("MSG:Demo 3")
                        controlar_pixel(2, 0, 0, 0)

                    # === LÓGICA DA TECLA 4 ===
                    elif tecla == '4':
                        # Demo: abrir aplicação (exemplo: Bloco de Notas)
                        # Pode substituir pelo executável da sua preferência
                        try:
                            subprocess.Popen(["notepad.exe"])
                            enviar_comando("MSG:Bloco Notas")
                        except Exception as e:
                            print(f"Erro ao abrir aplicação: {e}")
                            enviar_comando("MSG:Erro App")

                    # === LÓGICA DA TECLA 5 ===
                    elif tecla == '5':
                        # Demo: digitação de email / template predefinido
                        controlar_pixel(2, 100, 20, 60)
                        escrever_texto_seguro("demo.user@example.com")
                        enviar_comando("MSG:Demo Email")
                        controlar_pixel(2, 0, 0, 0)

                    # === LÓGICA DA TECLA 6 ===
                    elif tecla == '6':
                        # Demo: controlo de estado e LED (exemplo: Spotify / Media Play-Pause)
                        estado_pixels[1] = not estado_pixels[1]
                        if estado_pixels[1]:
                            controlar_pixel(1, 0, 255, 0) # LIGA VERDE
                            enviar_comando("MSG:Spotify")
                            # pyautogui.press('playpause') # Atalho multimédia opcional
                        else:
                            controlar_pixel(1, 0, 0, 0)   # DESLIGA
                            enviar_comando("MSG:Spotify OFF")

                    # === LÓGICA DA TECLA 7 ===
                    elif tecla == '7':
                        # Demo: controlo de estado e LED (exemplo: Mute Discord)
                        estado_pixels[2] = not estado_pixels[2]
                        if estado_pixels[2]:
                            controlar_pixel(2, 220, 20, 60) # LIGA AZUL
                            enviar_comando("MSG:Discord")
                        else:
                            controlar_pixel(2, 0, 0, 0)   # DESLIGA
                            enviar_comando("MSG:Desligado")

                    # === LÓGICA DA TECLA 8 ===
                    elif tecla == '8':
                        # Demo: silenciar/ativar som do sistema (Mute)
                        pyautogui.press('volumemute')
                        enviar_comando("MSG:Audio Mute")

                    # === LÓGICA DA TECLA 9 ===
                    elif tecla == '9':
                        # Demo: executar ferramenta (exemplo: Calculadora)
                        try:
                            subprocess.Popen(["calc.exe"])
                            enviar_comando("MSG:Calculadora")
                        except Exception as e:
                            print(f"Erro ao abrir executável: {e}")
                            enviar_comando("MSG:Erro Calc")
                            
        except Exception as e:
            print(f"Erro durante a leitura: {e}")
            continue

        time.sleep(0.01) # Pausa mínima para não sobrecarregar o CPU

    # Quando mandamos parar o serviço, fechamos a porta
    if arduino and arduino.is_open:
        arduino.close()
        print("Porta fechada.")
    definir_estado("parado")

# --- CONTROLOS DO SERVIÇO ---
def iniciar_servico():
    global thread_serial, a_correr
    if a_correr:
        return
    if thread_serial and thread_serial.is_alive():
        return
    a_correr = True
    definir_estado("a_iniciar")
    thread_serial = threading.Thread(target=ouvir_arduino, daemon=True)
    thread_serial.start()

def parar_servico():
    global a_correr, thread_serial
    a_correr = False # Faz o loop do 'ouvir_arduino' terminar
    if thread_serial:
        thread_serial.join(timeout=2)
    thread_serial = None
    definir_estado("parado")

# --- JANELA DE CONFIGURAÇÃO (Tkinter) ---
def criar_janela():
    root = tk.Tk()
    root.title("Configurar Arduino Macro")
    root.geometry("300x200")
    
    tk.Label(root, text="Porta COM:").pack(pady=5)
    
    portas_disponiveis = [port.device for port in serial.tools.list_ports.comports()]
    if not portas_disponiveis:
        portas_disponiveis = ["Nenhuma porta detetada"]
        
    combo_portas = ttk.Combobox(root, values=portas_disponiveis)
    combo_portas.set(porta_atual)
    combo_portas.pack(pady=5)
    
    tk.Label(root, text="Baud Rate:").pack(pady=5)
    combo_baud = ttk.Combobox(root, values=["4800", "9600", "19200", "115200"])
    combo_baud.set(str(baud_atual))
    combo_baud.pack(pady=5)
    
    def guardar():
        global porta_atual, baud_atual
        if combo_portas.get() != "Nenhuma porta detetada":
            porta_atual = combo_portas.get()
            baud_atual = int(combo_baud.get())

            try:
                guardar_configuracoes()
            except OSError as erro:
                messagebox.showerror(
                    "Erro",
                    f"Não foi possível guardar as configurações:\n{erro}"
                )
                return
             
            # Se já estiver a correr, pára e reinicia com a porta nova
            was_running = a_correr
            if was_running:
                parar_servico()
                time.sleep(1) # Dá tempo à porta COM de fechar bem
                iniciar_servico()
                
            messagebox.showinfo("Sucesso", f"Configurações guardadas!\nPorta: {porta_atual}")
            root.quit()    
            root.destroy()  
            
    tk.Button(root, text="Guardar e Aplicar", command=guardar).pack(pady=15)
    root.mainloop()

def abrir_configuracoes(icon, item):
    threading.Thread(target=criar_janela, daemon=True).start()

# --- ÍCONE DO SYSTEM TRAY ---
def criar_imagem_icone():
    image = Image.new('RGB', (64, 64), color=(0, 120, 215))
    dc = ImageDraw.Draw(image)
    dc.text((10, 20), "ARD", fill=(255, 255, 255)) 
    return image

def sair(icon, item):
    parar_servico()
    icon.stop()

def alternar_estado(icon, item):
    if servico_estado in ("a_iniciar", "ativo"):
        parar_servico()
    else:
        iniciar_servico()
    atualizar_menu()

# Menu do botão direito no ícone
menu = pystray.Menu(
    pystray.MenuItem("Configurações", abrir_configuracoes),
    pystray.MenuItem(lambda text: "Parar Serviço" if servico_estado in ("a_iniciar", "ativo") else "Iniciar Serviço", alternar_estado),
    pystray.MenuItem("Sair", sair)
)

# Inicia a aplicação
if __name__ == "__main__":
    carregar_configuracoes()
    iniciar_servico() 
    icone = pystray.Icon("ArduinoMacro", criar_imagem_icone(), "Arduino MacroKeys", menu)
    icone.run()
