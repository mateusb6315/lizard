# FFmpeg e FFprobe

Os executáveis locais informam a versão `N-128691-gcc583787bb-20261108`, com compilação compartilhada para Windows x64 e licença LGPLv3 ou posterior. A publicação correspondente à versão e à variante lista o arquivo `ffmpeg-N-128691-gcc583787bb-win64-lgpl-shared.zip`. [Publicação da build](https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/tag/autobuild-2026-11-08-12-35) · [Código-fonte](https://github.com/FFmpeg/FFmpeg/tree/cc583787bb)

Mantenha as DLLs junto aos dois executáveis em `tools/ffmpeg/`. Os hashes abaixo foram calculados sobre os arquivos locais e são usados pelo script de empacotamento.

- SHA-256 de ffmpeg.exe: `3b6be4d757d708271d17445cd275cb11d281fdb80ac3b7c97cb5771534b33c1e`.
- SHA-256 de ffprobe.exe: `aac93e4b0b9a55d456945099d06f457baff36590d976d0622e8f7270b12f491d`.
- SHA-256 de avcodec-63.dll: `14a861ebf44bca4b45707dce5ee4b8dc47b43793b040cc19e4d778ccf02c09fd`.
- SHA-256 de avdevice-63.dll: `42f1f49c42b9aa22c3bdf711ba844f78ac528133c73f9ca065aecb6d0fb2d9f6`.
- SHA-256 de avfilter-12.dll: `3b43ff0774501662bd12f811e40006d683a384c87ebf9612e218e2da51e582db`.
- SHA-256 de avformat-63.dll: `73c2da8fd14255a8d1f27ed0ac514c01e4120269d5b2ac74c7324e6e3dfad5a4`.
- SHA-256 de avutil-61.dll: `64b6b549a68094225deabc4ed69b37f99a2d41539e9ebf472df61af37a47a004`.
- SHA-256 de swresample-7.dll: `ddf34b1fec439197b4aa2dfb9894d5faf3d3c09189a6d7c7542ee0b4833856aa`.
- SHA-256 de swscale-10.dll: `f21a8a348329cf6e683887062650b9886a74d48cfb04001446bbc719a748d177`.

O texto da LGPLv3 acompanha os binários em [COPYING.LGPLv3](COPYING.LGPLv3), junto ao texto da GPLv3 incorporado por referência. O `README.txt` de Gyan Doshi descreve a build estática anterior. [Texto da GPLv3](LICENSE)

A build oferece `libopenh264` para recodificação em H.264. Os perfis declaram essa opção depois de `libx264`, que está ausente nesta compilação. Uma amostra sintética com vídeo FFV1 e áudio PCM foi recodificada com sucesso nos 31 perfis do catálogo.
