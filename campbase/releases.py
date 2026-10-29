# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Current release notes shared by the application and release exporter."""
from .i18n import _

RELEASE_VERSION = '0.1.0'


def introduction():
    return _("Primera versió del Campbase, el teu campament base per organitzar projectes.")


def sections():
    return [
        (_("Taulers i targetes"),
         _("Organitza els projectes amb columnes, targetes, etiquetes i dates límit. Escriu descripcions amb format i imatges, participa en els comentaris i esborra els teus quan calgui. Consulta el recompte de comentaris al costat del títol, sense afegir una fila a la targeta. El recompte del Campbase exclou les reaccions i queda centrat amb el títol.")),
        (_("Col·laboració als taulers"),
         _("Comparteix taulers i gestiona els permisos. Identifica els participants amb la seva imatge, assigna targetes i cita membres amb @, amb suggeriments i mencions ressaltades. Reacciona als comentaris amb sis emojis. Es desen com a respostes amb una menció per avisar-ne l'autor; Campbase les agrupa i altres clients les mostren com a comentaris. Més espai i una icona més clara per reaccionar als comentaris.")),
        (_("Enllaços i selecció"),
         _("Copia l'enllaç d'un tauler per enviar-lo als membres autoritzats. El selector de reaccions s'obre sense cap emoji seleccionat. Més espai entre el checkbox i l'avatar en assignar targetes, i recompte de comentaris alineat amb la icona. L'enllaç de suport segueix l'idioma de l'aplicació.")),
        (_("Notificacions a mà"),
         _("Consulta comentaris, mencions, assignacions i comparticions, també de les teves accions. Obre el lloc relacionat amb cada avís i esborra'ls individualment o tots de cop.")),
        (_("Dates i identitat"),
         _("Tria l'hora límit en hora local. Identifica els autors dels comentaris amb nom, icona, data i hora, i consulta el nom d'usuari del compte a Preferències.")),
        (_("Sincronització amb Nextcloud Deck"),
         _("Connecta el compte des de Comptes en línia de GNOME. Conserva els canvis sense connexió i sincronitza'ls de manera automàtica o manual. Les lectures són més àgils i els avisos s'actualitzen sense interrompre la sincronització de les targetes. Els moviments d'arxivades poden continuar després d'una interrupció de la connexió. Els moviments cap a les arxivades actualitzen només les targetes necessàries, sense restaurar-les temporalment. Els recomptes es reutilitzen des de la memòria cau i s'actualitzen en segon pla sense endarrerir els moviments de targetes.")),
        (_("Un espai al teu gust"),
         _("Personalitza els projectes i canvia el nom o el color de cada columna per separat. A la secció d'arxivades, restaura o esborra cada targeta des dels seus controls, o esborra-les en grup. Mostra-les i amaga-les sense tornar a l'inici del tauler. Esborra els taulers propis des de la barra lateral. Tria l'aparença, les columnes per fila, el tauler d'inici i la barra lateral.")),
        (_("Arxivades i filtres"),
         _("Mostra o amaga les arxivades a totes les columnes i ajusta-les després per separat. Arrossega-les entre columnes, restaura-les deixant-les a la zona normal i desfés els canvis recents. El filtre «Assignades a mi» és al costat de les accions del tauler. Les actualitzacions mantenen la posició de lectura.")),
        (_("Controls de targeta"),
         _("Arxiva i arrossega les targetes amb els controls de la dreta, en aquest ordre. Els avatars dels assignats cedeixen el lloc als controls amb una transició suau, també a les arxivades. Els títols aprofiten millor l'amplada. L'avatar al peu de l'editor identifica l'autor o el responsable. Un marcador mostra on deixar anar cada targeta. Els avatars es mantenen durant la sincronització. La vista es manté fixa mentre arrossegues una targeta.")),
        (_("Interfície més clara"),
         _("Menús amb separadors i dreceres visibles, modals ajustats al contingut i una icona d'enllaç més clara. Marges coherents en compartir taulers, tant durant la càrrega com amb els membres i els resultats de cerca. Papereres de targetes i taulers en vermell i un botó per cancel·lar l'esborrament d'un tauler. Capçaleres de columna sense tooltips d'autoria. Preferències separa el tema de la vista del tauler. En arrossegar cap a les arxivades, es mostra només el marcador necessari. Els menús de columna es mantenen oberts mentre arriben actualitzacions. Tanca Notificacions clicant fora del modal.")),
        (_("Sis idiomes, integrats a GNOME"),
         _("Interfície amb GTK4 i Adwaita, dreceres de teclat i canvi immediat entre català, euskera, gallec AGAL, castellà, occità aranès i anglès.")),
    ]
