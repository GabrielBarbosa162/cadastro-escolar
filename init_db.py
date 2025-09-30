from app import db, Escola, Serie, app

with app.app_context():
    db.create_all()
    if not Escola.query.first():
        db.session.add_all([Escola(nome="Escola A"), Escola(nome="Escola B")])
    if not Serie.query.first():
        db.session.add_all([Serie(nome="1º Ano"), Serie(nome="2º Ano"), Serie(nome="3º Ano")])
    db.session.commit()

print("Banco de dados criado e seeds inseridos com sucesso!")
