project('campbase', version: '0.1.2', meson_version: '>= 1.0')

pkgdatadir = get_option('prefix') / get_option('datadir') / 'campbase'
configuration = configuration_data()
configuration.set('pkgdatadir', pkgdatadir)
configure_file(input: 'data/campbase.in', output: 'campbase', configuration: configuration,
               install: true, install_dir: get_option('bindir'), install_mode: 'rwxr-xr-x')
install_subdir('campbase', install_dir: get_option('datadir') / 'campbase',
               exclude_directories: ['__pycache__'])
install_data('data/cat.cesk.Campbase.desktop', install_dir: get_option('datadir') / 'applications')
install_data('data/cat.cesk.Campbase.metainfo.xml', install_dir: get_option('datadir') / 'metainfo')
install_data('data/icons/cat.cesk.Campbase.svg', install_dir: get_option('datadir') / 'icons/hicolor/scalable/apps')
install_subdir('data/icons/hicolor/scalable/actions',
               install_dir: get_option('datadir') / 'icons/hicolor/scalable')
install_data('LICENSE', 'NOTICE', install_dir: get_option('datadir') / 'licenses/cat.cesk.Campbase')

subdir('po')
