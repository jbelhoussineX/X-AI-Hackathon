"""Point d’entrée de l’interface Streamlit de l’équipe.

Lancer depuis la racine : python -m streamlit run app.py
"""

def main():
    # Bootstrap only when the application is explicitly run, before UI imports.
    from src.runtime_config import load_runtime_config
    load_runtime_config()
    from frontend.interface_b import main as render
    render()


if __name__ == "__main__":
    main()
