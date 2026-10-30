# Campbase

[English](README.md)

El Campbase és una app kanban nativa de GNOME, feta amb GTK4 i libadwaita i
sincronitzada amb **Nextcloud Deck**. Organitza projectes amb targetes i columnes,
treballa amb altres persones i consulta els mateixos taulers amb Deck a Android.

**Versió actual: 0.1.3 — versió de desenvolupament.**

[Codi font](https://github.com/ceskfreixas/campbase) ·
[Errors i suggeriments](https://github.com/ceskfreixas/campbase/issues) ·
[Dona suport al projecte](https://ceskfreixas.aixeta.cat/ca/subscriptions)

## Què hi pots fer

- Organitzar taulers adaptables, situar la primera columna en una fila superior
  i triar un màxim d'1 a 6 columnes per fila. **Fet** és una columna normal.
- Crear, editar, arrossegar, ordenar, arxivar i restaurar targetes; cercar títols,
  descripcions i etiquetes; crear i canviar el nom de taulers i columnes.
- Mostrar les arxivades independentment a cada columna i esborrar-les individualment
  o en grup des d'una secció pròpia, amb confirmació. El nom i el color de columna
  tenen accions separades. Esborrar els taulers propis des de la barra lateral.
- Triar a Preferències si les arxivades es mostren a totes les columnes i reiniciar
  les excepcions; després, ajustar cada columna per separat. Arrossegar-hi una targeta per arxivar-la, també
  quan la secció és buida.
- Desfer un moviment o arxivament recent des del missatge de confirmació,
  també després de sincronitzar-lo. Moure les arxivades i restaurar-les deixant-les
  a la zona normal. Filtrar amb **Assignades a mi**, al costat de les accions del
  tauler. Conservar la posició de lectura quan s'actualitza la vista.
- Mantenir la vista fixa durant l'arrossegament, els menús de columna oberts
  mentre arriben actualitzacions i els avatars dels assignats durant la sincronització.
  Consultar un recompte discret de comentaris al costat del títol, sense afegir cap fila.
  Aquest recompte exclou les reaccions i es calcula en segon pla amb memòria cau.
- Compartir taulers amb usuaris del mateix servidor de Nextcloud. Triar accés
  de lectura o edició, gestionar permisos i retirar una compartició directa.
- Convidar usuaris d'altres servidors amb l'identificador federat quan tots dos
  servidors tinguin Deck 1.18 o posterior i la compartició federada habilitada.
- Obrir les converses de Talk des del tauler, enviar missatges directes als
  membres del servidor i convidar-los explícitament a un xat privat del tauler.
- Assignar targetes als membres del tauler i veure'n les icones al tauler.
  Les assignacions es conserven també en els esborranys sense connexió.
- Reaccionar als comentaris amb sis emojis. Campbase agrupa aquestes respostes
  breus i esmenta l'autor per avisar-lo amb el sistema de notificacions de Deck.
  Altres clients les mostren i les compten com a comentaris normals. Els avisos
  respecten les opcions de notificació del destinatari a Nextcloud.
- Llegir i escriure comentaris amb icona, nom, usuari, data i hora. El selector
  **@** permet citar els membres amb el format de Nextcloud i ressalta les mencions.
  Cada autor pot esborrar els seus comentaris amb confirmació.
- Consultar mencions, reaccions als teus comentaris, assignacions, venciments,
  taulers compartits amb tu i missatges de Talk, amb accés directe al lloc relacionat.
  Les accions pròpies i els canvis rutinaris del tauler no omplen la bústia.
- Utilitzar etiquetes i triar la data límit amb un calendari i una hora local.
- Escriure descripcions amb negreta, cursiva, subratllat, ratllat, títols, llistes,
  citacions, codi, enllaços i imatges; enganxar imatges i desfer o refer l'edició.
- Editar el nom del projecte, posar-hi una descripció curta, una imatge o una de
  les 32 icones d'Adwaita. Triar entre 16 colors per a les columnes.
- Sincronitzar automàticament o amb **F5**, treballar amb una memòria cau local
  i revisar els conflictes sense perdre els canvis pendents.
- Configurar el tauler d'inici, la barra lateral i el tema; consultar les dreceres.
  Preferències separa el tema a **Aparença** i les opcions de disposició i arxivades
  a **Vista del tauler**.

La interfície està disponible en **català, euskera, gallec AGAL, castellà, occità
aranès i anglès**. L'idioma es detecta automàticament, amb l'anglès com a alternativa.
Pots canviar-lo a l'instant des de Preferències sense perdre els esborranys oberts.

## Comptes, col·laboració i sincronització

El Campbase utilitza el compte de **Comptes en línia de GNOME**. A Preferències
s'hi mostren el nom d'usuari real de Nextcloud i el nom visible. No cal introduir
ni desar una contrasenya pròpia dins de l'app.

Les comparticions i els permisos requereixen connexió. Les edicions de targetes i
les assignacions es conserven a la cua de canvis. Si desactives la sincronització
automàtica, esperen fins que premis F5. Per defecte se sincronitza cada 45 segons;
pots triar intervals d'entre 30 segons i 10 minuts.

Des de Comparteix el tauler pots veure i copiar l'enllaç per als membres autoritzats.
Les invitacions locals i federades comparteixen una secció amb un selector de
servidor i un únic permís inicial.
L'enllaç no dona accés a nous usuaris ni fa públic el tauler.

L'activitat de Deck només es consulta com a evidència d'autoria; no es mostra
com a notificacions. Les accions pròpies tampoc no generen avisos locals.

Notificacions també inclou els avisos natius de Talk i obre la conversa corresponent.
Els avisos segueixen les preferències de Deck i Talk del servidor;
Talk aprofita la consulta existent, sense afegir peticions periòdiques.
Es consulten com a màxim un cop per minut durant la sincronització habitual;
des de la secció de notificacions pots actualitzar-les immediatament. L'app no
s'executa en segon pla quan està tancada.

La compartició federada passa pel servidor connectat; el Campbase no envia les
credencials al servidor del destinatari. Cal una configuració d'administrador
i versions compatibles de Deck als dos servidors.

La missatgeria requereix Nextcloud Talk amb l'API de converses v4. Els participants
del xat es gestionen a Talk: canviar els permisos del tauler no els afegeix ni els
retira automàticament. El responsable confirma els membres locals abans de crear
el grup; els canvis posteriors i els participants remots es gestionen a Talk.
Els esborranys es conserven localment i els enviaments dubtosos no es repeteixen
automàticament. Els missatges i els avisos utilitzen Talk, sense crear comentaris
a Deck. Les lectures del xat només s'executen mentre el modal és obert i no
aturen la sincronització de les targetes.

L'autoria de les creacions fetes amb el Campbase es desa localment i es pot
completar amb l'activitat disponible de Deck. Quan no consta el creador d'un
element antic, es mostra el propietari que ofereix Deck o s'indica que l'autoria
no està disponible. No s'atribueixen les columnes antigues al compte connectat.

Les descripcions, les imatges del projecte i els colors de columna són locals,
perquè Deck no ofereix camps sincronitzables per a aquesta presentació. El nom
del projecte, les targetes, les etiquetes, les assignacions i els comentaris sí
que es desen a Nextcloud. El subratllat es desa amb `<u>` i pot variar en altres
clients; el contingut HTML mai no s'executa.

## Dreceres

| Acció | Drecera |
|---|---|
| Mostra o amaga els taulers | F9 |
| Cerca al tauler | Ctrl+F |
| Sincronitza | F5 o Ctrl+R |
| Targeta nova | Ctrl+N |
| Preferències | Ctrl+P o Ctrl+, |
| Totes les dreceres | Ctrl+? |

## Instal·lació i proves

El projecte es publica com a codi font i inclou un manifest Flatpak. Encara no
està publicat a Flathub.

```sh
flatpak-builder --user --install --force-clean build cat.ceskfreixas.Campbase.json
flatpak run cat.ceskfreixas.Campbase
```

Per treballar des del codi font, consulta les dependències del [README anglès](README.md).
El mode de demostració utilitza dades de prova i una memòria cau temporal, sense
accedir a comptes reals:

```sh
python3 scripts/compile_translations.py
python3 -m campbase --demo
python3 -m unittest discover -s tests -v
```

Les dades privades del Flatpak es desen a `~/.var/app/cat.ceskfreixas.Campbase/`. Les
credencials les gestiona GNOME i les peticions autenticades no segueixen
redireccions. Les proves d'escriptura utilitzen un servidor HTTP local de prova.

Encara no hi ha gestió general de tots els adjunts, edició o eliminació
d'etiquetes ni una paperera pròpia.

## Projecte i llicència

El Campbase és programari lliure sota **GPL-3.0-or-later**. Consulta [LICENSE](LICENSE)
i [NOTICE](NOTICE). Copyright © 2026 Cesk Freixas. Les metadades són CC0-1.0;
les dependències mantenen les seves llicències. Les icones del sistema són d'Adwaita.
És una app independent, sense vinculació oficial amb Nextcloud ni GNOME.

A «Quant al Campbase» trobaràs les novetats de la versió, els crèdits, la web de
Cesk Freixas i un enllaç per donar suport al projecte. Les novetats es mantenen a
`campbase/releases.py` i s'exporten amb `scripts/release_notes.py`. El procés de
cada versió està recollit a [AGENTS.md](AGENTS.md).

Els adjunts es poden afegir i desar des de les targetes amb els selectors de
fitxers de GNOME (fins a 64 MiB). Els enviaments sense confirmar es revisen
abans de repetir-los. El gestor d'etiquetes permet canviar-ne el nom i el color
o esborrar-les amb confirmació. Els taulers esborrats recentment es poden
recuperar mentre Deck els conservi, també amb la icona i els colors locals.
A Talk es poden editar i esborrar missatges propis segons les capacitats i els
terminis del servidor. La memòria cau amb ETag és limitada i independent per
compte; s'invalida en escriure i no substitueix les comprovacions dels canvis.
