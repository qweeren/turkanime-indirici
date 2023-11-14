""" TürkAnimu Downloader """
from os import environ,name
from time import sleep
import sys
import atexit
from rich import print as rprint
import questionary as qa
from selenium.common.exceptions import WebDriverException
from easygui import diropenbox

from ..webdriver import create_webdriver,elementi_bekle
from ..objects import Anime, Bolum
from .dosyalar import Dosyalar
from .gereksinimler import Gereksinimler, MISSING
from .cli_tools import prompt_tema,clear,CliProgress

# Uygulama dizinini sistem PATH'ına ekle.
SEP = ";" if name=="nt" else ":"
environ["PATH"] +=  SEP + Dosyalar().ta_path + SEP

def gereksinim_kontrol_cli():
    """ Gereksinimleri kontrol eder ve gerekirse indirip kurar."""
    gerek = Gereksinimler()
    with CliProgress("Gereksinimler kontrol ediliyor.."):
        eksikler = gerek.eksikler
    if eksikler:
        eksik_msg = ""
        guide_msg = "\nManuel indirmek için:\nhttps://github.com/KebabLord/turkanime-indirici/wiki"
        for eksik,exit_code in eksikler:
            if exit_code is MISSING:
                eksik_msg += f"!) {eksik} yazılımı bulunamadı.\n"
            else:
                eksik_msg += f"!) {eksik} yazılımı bulundu ancak çalıştırılamadı.\n"
        print(eksik_msg,end="\n\n")
        if name=="nt" and qa.confirm("Otomatik kurulsun mu?").ask():
            with CliProgress("Güncel indirme linkleri getiriliyor.."):
                links = gerek.url_liste
            with CliProgress() as clip:
                fails = gerek.otomatik_indir(url_liste=links, callback=cli.callback)
            eksik_msg = ""
            for fail in fails:
                if "err_msg" in fail:
                    eksik_msg += f"!) {fail['name']} indirilemedi\n"
                    if fail["err_msg"] != "":
                        eksik_msg += f" - {fail['err_msg'][:55]}...\n"
                elif "ext_code" in fail:
                    if fail["ext_code"] is MISSING:
                        eksik_msg += f"!) {fail['name']} kurulamadı.\n"
                    else:
                        eksik_msg += f"!) {fail['name']} çalıştırılamadı.\n"
            if fails:
                print(eksik_msg + guide_msg)
                input("\n(ENTER'a BASIN)")
                sys.exit(1)
        else:
            print(guide_msg)
            input("\n(ENTER'a BASIN)")
            sys.exit(1)


def eps_to_choices(liste,mark_type=None):
    """ - [Bolum,] listesini `questionary.Choice` listesine dönüştürür.
        - Ayrıca geçmiş.json'daki izlenen/indirilen bölümlere işaret koyar.
    """
    assert len(liste) != 0 and isinstance(liste[0], Bolum)
    seri, choices, gecmis = liste[0].anime.slug, [], []
    if mark_type:
        gecmis_ = Dosyalar().gecmis
        if seri in gecmis_[mark_type]:
            gecmis = gecmis_[mark_type][seri]
    for bolum in liste:
        name = str(bolum.title)
        if bolum.slug in gecmis:
            name += " ●"
        choices += [qa.Choice(name,bolum)]
    return choices


def menu_loop(driver):
    """ Ana menü interaktif navigasyonu """
    while True:
        clear()
        islem = qa.select(
            "İşlemi seç",
            choices=['Anime izle',
                    'Anime indir',
                    'Ayarlar',
                    'Kapat'],
            style=prompt_tema,
            instruction=" "
        ).ask()
        # Anime izle veya indir seçildiyse.
        if "Anime" in islem:
            # Seriyi seç.
            try:
                with CliProgress("Anime listesi getiriliyor.."):
                    animeler = Anime.get_anime_listesi(driver)
                seri_ismi = qa.autocomplete(
                    'Animeyi yazın',
                    choices = [n for s,n in animeler],
                    style = prompt_tema
                ).ask()
                if seri_ismi is None:
                    continue
                seri_slug = [s for s,n in animeler if n==seri_ismi][0]
                anime = Anime(driver,seri_slug)
            except (KeyError,IndexError):
                rprint("[red][strong]Aradığınız anime bulunamadı.[/strong][red]")
                sleep(1.5)
                continue

            while True:
                dosya = Dosyalar()
                if "izle" in islem:
                    with CliProgress("Bölümler getiriliyor.."):
                        choices = eps_to_choices(anime.bolumler, mark_type="izlendi")
                    izlenen = [c for c in choices if c.title[-1] == "●"]
                    son_izlenen = izlenen[-1] if izlenen else None
                    bolum = qa.select(
                        message='Bölüm seç',
                        choices= choices,
                        style=prompt_tema,
                        default=son_izlenen
                    ).ask(kbi_msg="")
                    if not bolum:
                        break
                    fansubs, sub = bolum.fansubs, None
                    if dosya.ayarlar["manuel fansub"] and len(fansubs) > 1:
                        sub = qa.select(
                            message='Fansub seç',
                            choices= fansubs,
                            style=prompt_tema,
                        ).ask(kbi_msg="")
                    with CliProgress() as clip:
                        vids = bolum.filter_videos(
                            by_res=dosya.ayarlar["max çözünürlük"],
                            by_fansub=sub,
                            callback=clip.callback)
                    for i in range(3):
                        status = vids[i].oynat()
                        if status.returncode == 0:
                            break
                    dosya.set_gecmis(anime.slug, bolum.slug, "izlendi")
                else:
                    choices = eps_to_choices(anime.bolumler, mark_type="indirildi")
                    inen = [c for c in choices if c.title[-1] == "●"]
                    son_inen = inen[-1] if inen else None
                    bolumler = qa.checkbox(
                        message = "Bölüm seç",
                        choices=choices,
                        style=prompt_tema,
                        initial_choice=son_inen
                    ).ask(kbi_msg="")
                    if not bolumler:
                        break

        elif islem == "Ayarlar":
            while True:
                clear()
                dosyalar = Dosyalar()
                ayarlar = dosyalar.ayarlar
                tr = lambda opt: "AÇIK" if opt else "KAPALI" # Bool to Türkçe
                ayarlar_options = [
                    'İndirilenler klasörünü seç',
                    'İzlerken kaydet: '+tr(ayarlar['izlerken kaydet']),
                    'Manuel fansub seç: '+tr(ayarlar['manuel fansub']),
                    'İzlendi/İndirildi ikonu: '+tr(ayarlar["izlendi ikonu"]),
                    'Aynı anda indirme sayısı: '+str(ayarlar["aynı anda indirme sayısı"]),
                    'Geri dön'
                ]
                ayar_islem = qa.select(
                    'İşlemi seç',
                    ayarlar_options,
                    style=prompt_tema,
                    instruction=" "
                    ).ask()

                if ayar_islem == ayarlar_options[0]:
                    indirilenler_dizin=diropenbox()
                    if indirilenler_dizin:
                        dosyalar.set_ayar("indirilenler",indirilenler_dizin)
                elif ayar_islem == ayarlar_options[1]:
                    dosyalar.set_ayar("izlerken kaydet", not ayarlar['izlerken kaydet'])
                elif ayar_islem == ayarlar_options[2]:
                    dosyalar.set_ayar('manuel fansub', not ayarlar['manuel fansub'])
                elif ayar_islem == ayarlar_options[3]:
                    dosyalar.set_ayar('izlendi ikonu', not ayarlar['izlendi ikonu'])
                elif ayar_islem == ayarlar_options[4]:
                    max_dl = qa.text(
                        message = 'Maksimum eş zamanlı kaç bölüm indirilsin?',
                        default = str(ayarlar["aynı anda indirme sayısı"]),
                        style = prompt_tema
                    ).ask(kbi_msg="")
                    if isinstance(max_dl,str) and max_dl.isdigit():
                        dosyalar.set_ayar("aynı anda indirme sayısı", int(max_dl))
                else:
                    break

        elif islem == "Kapat":
            break


def main():
    # Gereksinimleri kontrol et
    gereksinim_kontrol_cli()

    # Selenium'u başlat.
    with CliProgress("Driver başlatılıyor.."):
        driver = create_webdriver(preload_ta=False)

    # Script herhangi bir sebepten dolayı sonlandırıldığında.
    def kapat():
        with CliProgress("Driver kapatılıyor.."):
            driver.quit()
    atexit.register(kapat)

    # Türkanime'ye bağlan.
    try:
        with CliProgress("Türkanime'ye bağlanılıyor.."):
            driver.get("https://turkanime.co/kullanici/anonim")
            elementi_bekle(".navbar-nav",driver)
    except (ConnectionError,WebDriverException):
        rprint("[red][strong]TürkAnime'ye ulaşılamıyor.[/strong][red]")
        sys.exit(1)

    # Navigasyon menüsünü başlat.
    clear()
    rprint("[green]!)[/green] Üst menülere dönmek için Ctrl+C kullanabilirsiniz.\n")
    sleep(1.7)
    menu_loop(driver)


if __name__ == '__main__':
    main()