# ProjetoAgenda

Sistema Flask para agendamento de salas, laboratorios e equipamentos escolares.

## Principios do Produto

- Professores entram apenas com CPF e permanecem conectados.
- Administradores entram com CPF e senha.
- A experiencia principal e mobile-first, mas a interface tambem deve funcionar bem em desktop.
- O sistema evita conflitos de recurso, turma e professor no mesmo horario.

## Estrutura

```text
agenda/
  app/
    static/
    templates/
    __init__.py
    admin.py
    controllers.py
    models.py
    security.py
  config.py
  requirements.txt
  run.py
  wsgi.py
```

## Rodando Localmente

```bash
cd agenda
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python seed_dados.py
python run.py
```

Acesse o endereço local exibido pelo servidor Flask no terminal.

Dados de exemplo:

- Admin: CPF `000.000.000-00`, senha `admin123`
- Professores: entram apenas com o CPF cadastrado no seed

## Variaveis de Ambiente

Copie `agenda/.env.example` para `agenda/.env` e ajuste conforme o ambiente.

Em producao, defina obrigatoriamente:

```env
ENV=production
DEBUG=False
SECRET_KEY=uma_chave_longa_e_aleatoria
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_SAMESITE=Lax
FORCE_HTTPS=True
TRUST_PROXY_HEADERS=True
TRUSTED_HOSTS=agenda.seudominio.com.br
```

O arquivo real `.env` deve permanecer fora do Git. Se uma chave secreta já
foi publicada no histórico do repositório, gere uma nova `SECRET_KEY` no
ambiente de produção.

## Admin Inicial

Para criar um administrador no primeiro boot:

```env
DEFAULT_ADMIN_ENABLED=True
DEFAULT_ADMIN_NOME=Administrador
DEFAULT_ADMIN_MATRICULA=00000000000
DEFAULT_ADMIN_SENHA=troque_essa_senha
```

Depois do primeiro acesso, desative `DEFAULT_ADMIN_ENABLED`.

## Produção

Use o entrypoint WSGI:

```bash
gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app
```

No Windows, use um servidor WSGI compativel, como Waitress, ou publique por uma plataforma que aceite `wsgi:app`.

Quando houver proxy reverso, ele deve encaminhar `Host`,
`X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Port` e
`X-Forwarded-For`. O arquivo `deploy/nginx-agenda.conf.example` contém uma
configuração de referência com redirecionamento permanente para HTTPS.

## Observacoes Tecnicas

- CSRF esta ativo para `POST`, `PUT`, `PATCH` e `DELETE`.
- O cookie de permanencia fica ativo para evitar que professores informem CPF a cada acesso.
- O banco padrao e SQLite em `agenda/agendamento.db`.
- Para evolucao mais robusta de schema, o proximo passo recomendado e adicionar Flask-Migrate/Alembic.
