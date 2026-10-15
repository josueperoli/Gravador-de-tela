# Gravador de Tela

Aplicativo leve para Windows que grava o desktop em MP4, com saída vertical
para Instagram Reels ou YouTube Shorts.

## Recursos

- Posicione uma moldura fixa 9:16 sobre a área da tela que deseja gravar.
- Use a grade de terços para ajustar o enquadramento; arraste a moldura e confirme pelo botão **Finalizar posicionamento** ou com `Enter`.
- Grave em MP4 a 1080 × 1920 e 30 FPS, codificado em H.264 de alta qualidade
  (CRF 16), compatível com Reels e Shorts.
- A moldura mantém o formato vertical fixo, e o vídeo é salvo em 1080 × 1920.
- O enquadramento inicial ocupa 80% da altura disponível, mantendo espaço para
  reposicioná-lo na tela. O redimensionamento usa interpolação de alta qualidade
  quando necessário.
- Os quadros são capturados e gravados um de cada vez, sem manter o vídeo todo na RAM.
- O áudio que toca na saída de som padrão do computador é gravado junto com o vídeo.
- O microfone não é gravado.

## Instalação e execução

Instale o Python 3.10 ou mais recente, incluindo o Tcl/Tk (normalmente incluído
no instalador oficial para Windows). No PowerShell, dentro desta pasta:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Para abrir o gravador com um clique, execute `Criar Atalho.ps1` uma vez. Ele cria
**Gravador de Tela.lnk** na Área de Trabalho. O iniciador abre o aplicativo sem
abrir uma janela de terminal e inicia o aplicativo em um processo independente:
usa `pythonw.exe` do ambiente `.venv` quando disponível ou `pyw.exe` do Python
Launcher como alternativa. Se já existir um atalho antigo, execute
`Criar Atalho.ps1` novamente para atualizá-lo. Fechar a janela do terminal usada
para executar `Iniciar Gravador.bat` não encerra o aplicativo.
Com o aplicativo aberto, pressione `Ctrl+Alt+R` para iniciar ou parar a gravação.

No aplicativo, selecione Instagram Reels ou YouTube Shorts para abrir a moldura
de enquadramento. Arraste-a para a área que deseja gravar e pressione `Enter`
ou clique em **Finalizar posicionamento** para voltar ao programa (`Esc` cancela).
Se necessário, use **Posicionar enquadramento**
para ajustar novamente. Depois, escolha onde salvar o MP4, clique em
**Iniciar gravação** e clique em **Parar** para finalizar o arquivo.

O gravador captura o áudio reproduzido na saída padrão do Windows. Para incluir
um som, deixe essa saída selecionada no Windows e reproduza o som durante a gravação.
