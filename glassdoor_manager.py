# glassdoor_manager.py
#
# Testa se o Glassdoor está funcionando no pipeline.
# O token CSRF é gerenciado internamente pelo JobSpy.
#
# Uso:
#   python glassdoor_manager.py

import sys
from jobspy import scrape_jobs


def test_glassdoor() -> bool:
    print("🔍 Testando busca no Glassdoor (United States)...")
    try:
        df = scrape_jobs(
            site_name=["glassdoor"],
            search_term="Android developer",
            location="United States",
            results_wanted=5,
            hours_old=72,
            country_indeed="USA",
        )

        if df is None or df.empty:
            print("⚠️  Busca retornou 0 vagas — Glassdoor pode estar bloqueando.")
            return False

        print(f"✅ {len(df)} vagas encontradas. Glassdoor funcionando.\n")
        for _, row in df.iterrows():
            print(f"  • {row.get('title', 'N/A')} — {row.get('company', 'N/A')} ({row.get('location', 'N/A')})")
        return True

    except Exception as e:
        print(f"❌ Erro: {e}")
        return False


if __name__ == "__main__":
    success = test_glassdoor()
    sys.exit(0 if success else 1)
