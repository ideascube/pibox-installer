# -*- mode: python -*-

import os
import site

block_cipher = None
typelib_path = os.path.join(site.getsitepackages()[1], 'gnome', 'lib', 'girepository-1.0')

a = Analysis(['pibox-installer/__main__.py'],
             pathex=['.'],
             datas=[('ui.glade', '.'),
                    ('contents.json', '.'),
                    ('pibox-installer-logo.png', '.'),
                    ('ansiblecube', 'ansiblecube'),
                    ('pibox-installer-vexpress-boot', 'pibox-installer-vexpress-boot'),
                    ('C:\Program Files\qemu', 'qemu'),
                    ('C:\Program Files\imdiskinst', 'imdiskinst'),
                    ('C:\Program Files\\7zextra\\x64\\7za.dll', '.'),
                    ('C:\Program Files\\7zextra\\x64\\7za.exe', '.'),
                    ('C:\Program Files\\7zextra\\x64\\7zxa.dll', '.')],
             hiddenimports=['gui', 'cli', 'image'],
             hookspath=['additional-hooks'],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [('v', None, 'OPTION')],
          exclude_binaries=False,
          name='launcher',
          debug=True,
          strip=False,
          upx=False,
          console=True,
          icon='pibox-installer-logo.ico',
          uac_admin=False)
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='kiwix-plug_installer')
