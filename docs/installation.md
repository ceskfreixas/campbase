# Install Campbase 0.1.4

[English](#english) · [Català](#català) · [Castellano](#castellano) · [Galego](#galego) · [Euskara](#euskara) · [Aranés](#aranés)

## English

Download `Campbase-0.1.4-x86_64.flatpak` and its `.sha256` file from the
[official release](https://github.com/ceskfreixas/campbase/releases/tag/0.1.4).
This development preview is for Linux x86_64. It requires Flatpak and a Nextcloud
account with Deck configured in GNOME Online Accounts. Conversations additionally
require Nextcloud Talk.

In the download directory, verify the file, install it and open Campbase:

```sh
sha256sum -c Campbase-0.1.4-x86_64.flatpak.sha256
flatpak install --user ./Campbase-0.1.4-x86_64.flatpak
flatpak run --user --branch=master cat.ceskfreixas.Campbase
```

Flatpak may download the GNOME 50 runtime from Flathub on first installation;
the runtime is larger than the Campbase file. Campbase itself is not on Flathub.
You can also open the `.flatpak` file with your software manager if it supports
local Flatpak files.

Campbase updates are manual: download a newer bundle from the official releases
and install it with `flatpak install --user --reinstall ./FILE.flatpak`.
This retains application data. These bundles do not configure an automatic
Campbase update repository. The checksum checks file integrity; download both
files from the official release page.

## Català

Descarrega `Campbase-0.1.4-x86_64.flatpak` i el fitxer `.sha256` de la
[versió oficial](https://github.com/ceskfreixas/campbase/releases/tag/0.1.4).
És una versió de desenvolupament per a Linux x86_64. Cal tenir Flatpak i un compte
de Nextcloud amb Deck configurat als Comptes en línia del GNOME. Les converses
requereixen també Nextcloud Talk.

A la carpeta de descàrregues, comprova el fitxer, instal·la'l i obre el Campbase:

```sh
sha256sum -c Campbase-0.1.4-x86_64.flatpak.sha256
flatpak install --user ./Campbase-0.1.4-x86_64.flatpak
flatpak run --user --branch=master cat.ceskfreixas.Campbase
```

En la primera instal·lació, Flatpak pot descarregar l'entorn GNOME 50 des de
Flathub; aquest entorn ocupa més que el fitxer del Campbase. El Campbase encara
no està publicat a Flathub. També pots obrir el fitxer `.flatpak` amb el gestor
de programari si admet aquests fitxers locals.

Les actualitzacions són manuals: descarrega un paquet més recent de les versions
oficials i instal·la'l amb `flatpak install --user --reinstall ./FITXER.flatpak`.
Es conserven les dades de l'app. Aquests paquets no configuren cap repositori
d'actualització automàtica del Campbase. La suma de verificació comprova la
integritat del fitxer; descarrega tots dos fitxers de la pàgina oficial de la versió.

## Castellano

Descarga `Campbase-0.1.4-x86_64.flatpak` y el archivo `.sha256` de la
[versión oficial](https://github.com/ceskfreixas/campbase/releases/tag/0.1.4).
Es una versión de desarrollo para Linux x86_64. Requiere Flatpak y una cuenta de
Nextcloud con Deck configurada en las Cuentas en línea de GNOME. Las conversaciones
requieren también Nextcloud Talk.

En la carpeta de descargas, comprueba el archivo, instálalo y abre Campbase:

```sh
sha256sum -c Campbase-0.1.4-x86_64.flatpak.sha256
flatpak install --user ./Campbase-0.1.4-x86_64.flatpak
flatpak run --user --branch=master cat.ceskfreixas.Campbase
```

En la primera instalación, Flatpak puede descargar el entorno GNOME 50 desde
Flathub; este entorno ocupa más que el archivo de Campbase. Campbase todavía no
está publicado en Flathub. También puedes abrir el archivo `.flatpak` con el
gestor de software si admite estos archivos locales.

Las actualizaciones son manuales: descarga un paquete más reciente de las versiones
oficiales e instálalo con `flatpak install --user --reinstall ./ARCHIVO.flatpak`.
Se conservan los datos de la aplicación. Estos paquetes no configuran un repositorio
de actualización automática de Campbase. La suma de verificación comprueba la
integridad del archivo; descarga ambos archivos de la página oficial de la versión.

## Galego

Descarrega `Campbase-0.1.4-x86_64.flatpak` e o ficheiro `.sha256` da
[versão oficial](https://github.com/ceskfreixas/campbase/releases/tag/0.1.4).
É uma versão de desenvolvimento para Linux x86_64. Requer Flatpak e uma conta de
Nextcloud com Deck configurada nas Contas em linha do GNOME. As conversas requerem
também Nextcloud Talk.

Na pasta de descargas, verifica o ficheiro, instala-o e abre o Campbase:

```sh
sha256sum -c Campbase-0.1.4-x86_64.flatpak.sha256
flatpak install --user ./Campbase-0.1.4-x86_64.flatpak
flatpak run --user --branch=master cat.ceskfreixas.Campbase
```

Na primeira instalação, Flatpak pode descarregar o ambiente GNOME 50 do Flathub;
esse ambiente ocupa mais que o ficheiro do Campbase. O Campbase ainda não está
publicado no Flathub. Também podes abrir o ficheiro `.flatpak` com o gestor de
software se admitir estes ficheiros locais.

As atualizações são manuais: descarrega um pacote mais recente das versões oficiais
e instala-o com `flatpak install --user --reinstall ./FICHEIRO.flatpak`.
Conservam-se os dados da aplicação. Estes pacotes não configuram um repositório
de atualização automática do Campbase. A soma de verificação comprova a integridade
do ficheiro; descarrega ambos os ficheiros da página oficial da versão.

## Euskara

Deskargatu `Campbase-0.1.4-x86_64.flatpak` eta `.sha256` fitxategia
[bertsio ofizialetik](https://github.com/ceskfreixas/campbase/releases/tag/0.1.4).
Linux x86_64rako garapen-bertsioa da. Flatpak eta Deck duen Nextcloud kontu bat
behar dira, GNOMEren lineako kontuetan konfiguratuta. Elkarrizketetarako Nextcloud
Talk ere behar da.

Deskargen karpetan, egiaztatu fitxategia, instalatu eta ireki Campbase:

```sh
sha256sum -c Campbase-0.1.4-x86_64.flatpak.sha256
flatpak install --user ./Campbase-0.1.4-x86_64.flatpak
flatpak run --user --branch=master cat.ceskfreixas.Campbase
```

Lehen instalazioan, Flatpakek GNOME 50 ingurunea deskarga dezake Flathubetik;
inguruneak Campbaseren fitxategiak baino gehiago hartzen du. Campbase oraindik ez
dago Flathuben argitaratuta. `.flatpak` fitxategia zure software-kudeatzailearekin
ere ireki dezakezu, tokiko fitxategi horiek onartzen baditu.

Eguneratzeak eskuzkoak dira: deskargatu pakete berriago bat bertsio ofizialetatik
eta instalatu `flatpak install --user --reinstall ./FITXATEGIA.flatpak` erabiliz.
Aplikazioaren datuak gordetzen dira. Pakete hauek ez dute Campbase automatikoki
eguneratzeko biltegirik konfiguratzen. Egiaztapen-baturak fitxategiaren osotasuna
egiaztatzen du; deskargatu bi fitxategiak bertsioaren orri ofizialetik.

## Aranés

Descarrega `Campbase-0.1.4-x86_64.flatpak` e eth fichèr `.sha256` dera
[version oficiau](https://github.com/ceskfreixas/campbase/releases/tag/0.1.4).
Ei ua version de desvolopament entà Linux x86_64. Cau auer Flatpak e un compde de
Nextcloud damb Deck configurat enes Compdes en linha de GNOME. Es convèrses
requerissen tanben Nextcloud Talk.

Ena carpeta de descargues, verifica eth fichèr, installa-lo e daurís eth Campbase:

```sh
sha256sum -c Campbase-0.1.4-x86_64.flatpak.sha256
flatpak install --user ./Campbase-0.1.4-x86_64.flatpak
flatpak run --user --branch=master cat.ceskfreixas.Campbase
```

Ena prumèra installacion, Flatpak pòt descargar er entorn GNOME 50 de Flathub;
aguest entorn ocupe mès qu'eth fichèr deth Campbase. Eth Campbase encara non ei
publicat en Flathub. Tanben pòs daurir eth fichèr `.flatpak` damb eth gestor de
programari s'admet aguesti fichèrs locaus.

Es actualizacions son manuaus: descarrega un paquet mès recent des versions
oficiaus e installa-lo damb `flatpak install --user --reinstall ./FICHÈR.flatpak`.
Se consèrven es donades dera aplicacion. Aguesti paquets non configuren cap
repositori d'actualizacion automatica deth Campbase. Era soma de verificacion
comprove era integritat deth fichèr; descarrega es dus fichèrs dera pagina
oficiau dera version.
