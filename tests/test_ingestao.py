import json

from servicos.ingestao.chunking import carregar_diretorio, dividir
from servicos.ingestao.indice import Indice


def test_acumula_e_deduplica(tmp_path):
    ind = Indice(str(tmp_path / "i.json"))
    assert ind.adicionar([{"texto": "gatos miam", "origem": "a"}]) == {"novos": 1, "total": 1}
    r = ind.adicionar([{"texto": "gatos   miam", "origem": "b"},   # mesmo hash
                       {"texto": "cachorros latem", "origem": "b"}])
    assert r == {"novos": 1, "total": 2}


def test_persiste_apos_reiniciar(tmp_path):
    caminho = str(tmp_path / "i.json")
    Indice(caminho).adicionar([{"texto": "raft elege lider", "origem": "r"}])
    novo = Indice(caminho)  # "reinicio"
    assert [i["texto"] for i in novo.itens()] == ["raft elege lider"]
    novo.adicionar([{"texto": "cap trata de particoes", "origem": "c"}])
    assert Indice(caminho).total() == 2


def test_vetores_reindexados_com_mesma_dimensao(tmp_path):
    ind = Indice(str(tmp_path / "i.json"))
    ind.adicionar([{"texto": "alfa beta", "origem": "a"}])
    ind.adicionar([{"texto": "gama delta epsilon", "origem": "b"}])
    dims = {len(i["vetor"]) for i in ind.itens()}
    assert len(dims) == 1


def test_escrita_atomica_sem_tmp_residual(tmp_path):
    ind = Indice(str(tmp_path / "i.json"))
    ind.adicionar([{"texto": "x y z", "origem": "a"}])
    assert sorted(p.name for p in tmp_path.iterdir()) == ["i.json"]
    assert json.loads((tmp_path / "i.json").read_text())["itens"][0]["origem"] == "a"


def test_leitor_enxerga_escrita_de_outro_processo(tmp_path):
    caminho = str(tmp_path / "i.json")
    leitor, escritor = Indice(caminho), Indice(caminho)
    assert leitor.total() == 0
    escritor.adicionar([{"texto": "novo doc", "origem": "w"}])
    assert leitor.total() == 1


def test_chunking_paragrafos_e_arquivos(tmp_path):
    assert dividir("p1.\n\np2.") == ["p1.", "p2."]
    longo = " ".join(["Frase de teste numero um."] * 40)
    assert all(len(t) <= 520 for t in dividir(longo))
    (tmp_path / "x.txt").write_text("a\n\nb", encoding="utf-8")
    assert carregar_diretorio(str(tmp_path)) == [
        {"texto": "a", "origem": "x.txt"}, {"texto": "b", "origem": "x.txt"}]
