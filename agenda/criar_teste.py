import sqlite3

# Conecta ao banco de dados
conn = sqlite3.connect('agendamento.db')

try:
    # Executa o comando para adicionar a coluna
    conn.execute("ALTER TABLE recursos ADD COLUMN icone VARCHAR(50) DEFAULT 'bi-door-open'")
    conn.commit()
    print("✅ Sucesso: Coluna 'icone' adicionada ao banco de dados!")
except Exception as e:
    print(f"⚠️ Aviso: {e}")
finally:
    conn.close()