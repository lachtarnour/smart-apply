"""Domain catalog and classification for contact lookup."""

from __future__ import annotations

from urllib.parse import urlparse

ATS_DOMAINS = {
    # Greenhouse / Lever / Ashby
    "greenhouse.com",
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    # Workday / Oracle / SAP / UKG
    "myworkdayjobs.com",
    "oraclecloud.com",
    "successfactors.com",
    "successfactors.eu",
    "taleo.com",
    "taleo.net",
    "ukg.com",
    "ultipro.com",
    "workdayjobs.com",
    # SmartRecruiters / Workable / Recruitee / Teamtailor
    "smartrecruiters.com",
    "smartrecruiters.eu",
    "workable.com",
    "recruitee.com",
    "teamtailor.com",
    # Jobvite / JazzHR / ApplyToJob / iCIMS
    "applytojob.com",
    "icims.com",
    "jazz.co",
    "jazzhr.com",
    "jobvite.com",
    # Common SMB / Europe ATS
    "bamboohr.com",
    "altays-progiciels.com",
    "adequasys.com",
    "beetween.com",
    "breezy.hr",
    "contactrh.com",
    "comeet.co",
    "flatchr.io",
    "gestmax.fr",
    "homerun.co",
    "intervieweb.it",
    "jobaffinity.fr",
    "jobylon.com",
    "jometer.com",
    "join.com",
    "mstaff.co",
    "mytalentplug.com",
    "odoo.com",
    "personio.com",
    "pinpointhq.com",
    "recruitmentplatform.com",
    "skeeled.com",
    "softy.pro",
    "taleez.com",
    "talent-soft.com",
    "talentview.io",
    "werecruit.io",
    "welcomekit.co",
    "wink-lab.com",
    "zoho.com",
    "zohorecruit.com",
    # Other ATS / apply platforms observed in data
    "aplitrak.com",
    "easyapply.jobs",
    "nicoka.com",
    "smrtr.io",
    "trakstar.com",
    "aio-jobs.com",
    "xtramile.io",
    # Broad ATS / recruiting platforms from public ATS integration lists.
    "99jobs.com",
    "adp.com",
    "aptrack.co",
    "asuresoftware.com",
    "avature.net",
    "beamery.com",
    "beisen.com",
    "betterteam.com",
    "bigredsky.com",
    "bizneo.com",
    "brassring.com",
    "brightmove.com",
    "bullhorn.com",
    "cadienttalent.com",
    "candidatus.com",
    "careerpuck.com",
    "careerplug.com",
    "caselle.com",
    "catsone.com",
    "caypro.io",
    "cegid.com",
    "ceipal.com",
    "ceridian.com",
    "chaze.io",
    "clearcompany.com",
    "cloudoffix.com",
    "comeet.com",
    "compleet.com",
    "compleo.com.br",
    "cornerstoneondemand.com",
    "csod.com",
    "ctcpeople.com",
    "cvwarehouse.com",
    "darwinbox.com",
    "dayforcehcm.com",
    "deltek.com",
    "digitalrecruiters.com",
    "dvinci.de",
    "earcu.com",
    "eddy.com",
    "eightfold.ai",
    "elevatosoftware.com",
    "elmosoftware.com.au",
    "employmenthero.com",
    "emply.com",
    "empregare.com.br",
    "exacthire.com",
    "expr3ss.com",
    "factorial.co",
    "factorialhr.com",
    "flowtrack.ai",
    "fohandboh.com",
    "fountain.com",
    "freshteam.com",
    "freshworks.com",
    "gem.com",
    "gethired.com",
    "getonbrd.com",
    "glowinthecloud.com",
    "gohire.io",
    "gohiring.com",
    "goturbo.com.au",
    "governmentjobs.com",
    "gr8people.com",
    "graylink.biz",
    "greythr.com",
    "gupy.io",
    "halaxia.com",
    "harri.com",
    "hcms.ai",
    "heyjobs.co",
    "heyrecruit.de",
    "hibob.com",
    "higherme.com",
    "hirebridge.com",
    "hireclick.com",
    "hireground.us",
    "hirehive.com",
    "hireology.com",
    "hireroad.com",
    "hireserve.com",
    "hirewand.com",
    "hiringroom.com",
    "hiringthing.com",
    "hrlocker.com",
    "hrpanda.co",
    "hrweb.com",
    "idibu.com",
    "idealtraits.com",
    "in-recruiting.com",
    "infinite.com",
    "infor.com",
    "inhire.com.br",
    "intalent.ai",
    "intellihire.com",
    "invision-inc.jp",
    "iris.co.uk",
    "ismartrecruit.com",
    "isolvedhcm.com",
    "jobadder.com",
    "jobconvo.com",
    "jobdiva.com",
    "jobflows.co",
    "jobit.nl",
    "jobscore.com",
    "jobseeqr.co",
    "jobsoid.com",
    "jobtarget.com",
    "jobtrain.co.uk",
    "jxt.com.au",
    "karirpad.com",
    "keka.com",
    "keldairhr.com",
    "kenjo.io",
    "kenoby.com",
    "kolab.com.br",
    "kretos.cc",
    "kula.ai",
    "layan.eu",
    "livehire.com",
    "logicmelon.com",
    "loxo.co",
    "manatal.com",
    "martianlogic.com",
    "megahr.com",
    "mhrglobal.com",
    "mindscope.com",
    "mokahr.io",
    "mynexthire.com",
    "mystaffingpro.com",
    "myworkdaysite.com",
    "ncorehr.com",
    "neoed.com",
    "occupop.com",
    "oleeo.com",
    "onapply.de",
    "oorwin.com",
    "otys.com",
    "pageuppeople.com",
    "pandape.com.br",
    "paradox.ai",
    "paychex.com",
    "paycom.com",
    "paycor.com",
    "paylocity.com",
    "pcrecruiter.net",
    "peoplehum.com",
    "peoplestrong.com",
    "pereless.com",
    "performahrm.com",
    "phenom.com",
    "phenompeople.com",
    "pitchnhire.com",
    "plooral.com",
    "pockethrms.com",
    "polymer.co",
    "portalsinergyrh.com.br",
    "prevuehr.com",
    "pulsesoftware.com",
    "pyjamahr.com",
    "quickin.io",
    "raretechnology.com",
    "readytechworkforce.io",
    "recooty.com",
    "recruiterflow.com",
    "recruiterpm.com",
    "recruitive.com",
    "recruitlab.com",
    "recruitly.io",
    "recruitmenttechnologies.com",
    "recruitonline.com.au",
    "recruitrifle.com",
    "recrut.ai",
    "recrutei.com.br",
    "reczee.com",
    "redroverk12.com",
    "revolutpeople.com",
    "rexx-systems.com",
    "rezoomo.com",
    "rhgestor.com.br",
    "ripplehire.com",
    "rippling.com",
    "saba.com",
    "scope-recruiting.de",
    "scoptalent.com",
    "scouttalenthq.com",
    "seemehired.com",
    "selecty.com.br",
    "senior.com.br",
    "sensehq.com",
    "sesamehr.com",
    "shazamme.com",
    "sherlockhr.com",
    "shortlist.net",
    "silkroadtechnology.com",
    "simplicant.com",
    "simplyrecruit.in",
    "skeel.com.br",
    "smartcv.co",
    "smartsearchinc.com",
    "snaphire.com",
    "snaphop.com",
    "snaphunt.com",
    "softgarden.com",
    "softgarden.io",
    "solides.com.br",
    "sopea.com",
    "springboard.com.au",
    "sprouts.ai",
    "supportfinity.com",
    "sydle.com",
    "symphonytalent.com",
    "symplr.com",
    "talana.com",
    "talenta.co",
    "talent360.io",
    "talentats.ai",
    "talentbrand.com.br",
    "talentclue.com",
    "talenteca.com",
    "talentech.com",
    "talentfinder.be",
    "talention.com",
    "talentlyft.com",
    "talentnest.com",
    "talentplug.com",
    "talentplus.com",
    "talentrecruit.com",
    "talentreef.com",
    "talentsoft.com",
    "talentview.com",
    "talos360.co.uk",
    "tamrecruiting.com",
    "taqe.com.br",
    "targetrecruit.com",
    "teamdash.com",
    "teamio.com",
    "teamworkonline.com",
    "tellent.com",
    "thetalentpool.co.in",
    "topechelon.com",
    "traffit.com",
    "tribepad.com",
    "trinethire.com",
    "turbohire.co",
    "umantis.com",
    "unvyl.com",
    "varbi.com",
    "vasitum.com",
    "vidcruiter.com",
    "vivahr.com",
    "voyse.io",
    "wearemercury.com",
    "webbtree.com",
    "werecruit.com",
    "whoco.com",
    "wizehire.com",
    "worcket.com",
    "workbright.com",
    "workday.com",
    "worked.com.br",
    "workland.com",
    "workllama.com",
    "workwolf.com",
    "x0pa.com",
    "yaggo.co",
    "zapidhire.com",
    "zappyhire.com",
    "zazos.com",
    "zenats.com",
    "zimyo.com",
    "zwayam.com",
}

PARTNER_JOB_BOARD_DOMAINS = {
    # France Travail / public
    "candidat.francetravail.fr",
    "francetravail.fr",
    "gouv.fr",
    "pole-emploi.fr",
    # France major job boards
    "adzuna.com",
    "adzuna.fr",
    "apec.fr",
    "cadremploi.fr",
    "cadreo.com",
    "efinancialcareers.fr",
    "engineering.jobs",
    "glassdoor.com",
    "hellowork.com",
    "indeed.com",
    "indeed.fr",
    "jobijoba.com",
    "jobleads.com",
    "keljob.com",
    "linkedin.com",
    "meteojob.com",
    "monster.com",
    "monster.fr",
    "ouestjob.com",
    "pacajob.com",
    "parisjob.com",
    "regionsjob.com",
    "rhonealpesjob.com",
    "studentjob.fr",
    "sudouestjob.com",
    "talent-r.com",
    "talent.com",
    "welcometothejungle.com",
    # Tech / specialist boards
    "chooseyourboss.com",
    "aerocontact.com",
    "dogfinance.com",
    "emploi-pro.fr",
    "free-work.com",
    "moovijob.com",
    "lesjeudis.com",
    "linkfinance.fr",
    # Inclusion / handicap / sector partners
    "agefiph.asso.fr",
    "agefiph.fr",
    "apecita.com",
    "clicandsport.fr",
    "clicandearth.fr",
    "handicap-job.com",
    "handicap.fr",
    "jobinlive.com",
    "jobinlive.fr",
    "lindustrie-recrute.fr",
    "missionhandicap.com",
    "talents-handicap.com",
    # Aggregators / partner posting
    "batiactu.com",
    "bebee.com",
    "carriereonline.com",
    "careerjet.com",
    "directemploi.com",
    "emploi-collectivites.fr",
    "equest.com",
    "google.com",
    "jobposting.pro",
    "jobtransport.com",
    "jobvitae.fr",
    "jooble.org",
    "michaelpage.fr",
    "optioncarriere.com",
    "ouest-france.fr",
    "pmejob.fr",
    "trabajo.org",
}

APPLICATION_REDIRECT_DOMAINS = {
    "app.link",
    "bit.ly",
    "lnkd.in",
    "t.co",
    "tinyurl.com",
    "urlr.me",
}

NON_COMPANY_CONTACT_DOMAINS = (
    ATS_DOMAINS | PARTNER_JOB_BOARD_DOMAINS | APPLICATION_REDIRECT_DOMAINS
)

SUSPECT_CONTACT_DOMAIN_MARKERS = {
    "applicant",
    "apply",
    "ashby",
    "ats",
    "career",
    "careers",
    "candidate",
    "emploi",
    "greenhouse",
    "hiring",
    "icims",
    "job",
    "jobs",
    "lever",
    "recruit",
    "recrut",
    "smartrecruit",
    "taleo",
    "talent",
    "teamtailor",
    "workable",
    "workday",
}

def domain_from_url(url: str | None) -> str | None:
    """Return a normalized root-ish domain from an http(s) URL."""
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    host = parsed.netloc.split("@")[-1].split(":")[0].lower().removeprefix("www.")
    parts = [p for p in host.split(".") if p]
    if len(parts) <= 2:
        return host
    multi_part_suffixes = {
        ("co", "uk"),
        ("com", "au"),
        ("com", "br"),
        ("com", "tr"),
        ("com", "fr"),
        ("co", "jp"),
        ("asso", "fr"),
    }
    if len(parts) >= 3 and tuple(parts[-2:]) in multi_part_suffixes:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def normalize_domain(domain: str | None) -> str:
    return str(domain or "").lower().strip().removeprefix("www.")


def is_known_domain(domain: str | None, known_domains: set[str]) -> bool:
    normalized = normalize_domain(domain)
    if not normalized:
        return False
    return any(
        normalized == known or normalized.endswith(f".{known}")
        for known in known_domains
    )


def classify_application_domain(domain: str | None) -> str:
    normalized = normalize_domain(domain)
    if is_known_domain(normalized, ATS_DOMAINS):
        return "ats"
    if is_known_domain(normalized, PARTNER_JOB_BOARD_DOMAINS):
        return "partner_job_board"
    if is_known_domain(normalized, APPLICATION_REDIRECT_DOMAINS):
        return "application_redirect"
    return "unknown"


def is_company_domain(domain: str | None) -> bool:
    if not domain:
        return False
    domain = domain.lower().removeprefix("www.")
    return not is_job_board_domain(domain)


def is_job_board_domain(domain: str | None) -> bool:
    return is_known_domain(domain, NON_COMPANY_CONTACT_DOMAINS)


def is_suspicious_contact_domain(domain: str | None) -> bool:
    """Return True for domains that look like recruitment platforms."""
    if not domain:
        return False
    labels = [
        label
        for label in domain.lower().removeprefix("www.").split(".")
        if label
    ]
    searchable = labels[:-1] if len(labels) > 1 else labels
    return any(
        marker in label
        for label in searchable
        for marker in SUSPECT_CONTACT_DOMAIN_MARKERS
    )


def is_reliable_company_domain(domain: str | None) -> bool:
    return is_company_domain(domain) and not is_suspicious_contact_domain(domain)


def normalize_company_name(company: str) -> str:
    return " ".join((company or "").strip().lower().split())


def contact_lookup_key(company: str, application_url: str | None) -> str:
    domain = domain_from_url(application_url)
    if is_reliable_company_domain(domain):
        return f"domain:{domain}"
    normalized = normalize_company_name(company)
    return f"company:{normalized}" if normalized else "company:unknown"
