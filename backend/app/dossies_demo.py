"""Dossiês fictícios do Cofre Ambiental, carregados por ``python -m app.inicializar``.

Cada dossiê possui recortes independentes por nível (não cumulativos):
- nível 1 (permissão geral): resumo autorizado e orientações aos servidores;
- nível 2 (diretor de divisão): dados administrativos, pendências e histórico da divisão;
- nível 3 (ministro): síntese estratégica e decisões pendentes.

O conteúdo é administrativo e demonstrativo: não descreve substâncias, produção,
transporte, manipulação ou contenção de toxinas.
"""
from datetime import date

D = date

DOSSIES_DEMONSTRATIVOS = [
    {
        'codigo': 'DOS-2026-014',
        'titulo': 'Ocorrência ambiental na Região Alfa',
        'situacao': 'Em análise',
        'divisao': 'Divisão de Monitoramento Ambiental',
        'atualizado_em': D(2026, 11, 2),
        'recortes': {
            1: {
                'resumo': 'Ocorrência ambiental registrada na Região Alfa e acompanhada pela divisão '
                          'responsável. Não há orientação adicional para os servidores neste momento.',
                'orientacao': 'Encaminhe dúvidas somente pelos canais internos e não compartilhe este '
                              'resumo fora do sistema.',
                'campos': [
                    ('Situação para servidores', 'Em acompanhamento'),
                    ('Canal de contato', 'Ouvidoria interna do Cofre Ambiental'),
                    ('Próxima atualização prevista', '05/11/2026'),
                ],
                'historico': [
                    (D(2026, 10, 30), 'Dossiê aberto e comunicado inicial publicado.'),
                    (D(2026, 11, 2), 'Resumo autorizado atualizado para os servidores.'),
                ],
            },
            2: {
                'resumo': 'Relatório de campo recebido e em revisão administrativa. Duas pendências '
                          'precisam ser concluídas antes do envio ao gabinete do ministro.',
                'orientacao': 'Atualize o andamento somente pelo fluxo interno da divisão e mantenha um '
                              'responsável definido para cada pendência.',
                'campos': [
                    ('Coordenação responsável', 'Coordenação de Monitoramento'),
                    ('Equipe designada', 'Equipe técnica 3'),
                    ('Prazo da revisão', '06/11/2026'),
                    ('Classificação', 'Restrito à diretoria da divisão'),
                ],
                'pendencias': [
                    ('Revisar o relatório de campo',
                     'Conferir os dados e anexos enviados pela equipe técnica.', D(2026, 11, 4), 'Aberta'),
                    ('Validar a cadeia de custódia documental',
                     'Confirmar os registros de recebimento e as assinaturas dos documentos.',
                     D(2026, 11, 6), 'Aberta'),
                    ('Atualizar a matriz de responsáveis',
                     'Matriz revisada e publicada para a equipe.', D(2026, 10, 31), 'Concluída'),
                ],
                'historico': [
                    (D(2026, 10, 30), 'Dossiê aberto pela Divisão de Monitoramento Ambiental.'),
                    (D(2026, 10, 31), 'Equipe técnica 3 designada para o acompanhamento.'),
                    (D(2026, 11, 1), 'Relatório de campo encaminhado para revisão.'),
                    (D(2026, 11, 2), 'Revisão administrativa iniciada.'),
                ],
            },
            3: {
                'resumo': 'Situação sob controle administrativo, sem impacto externo confirmado. A divisão '
                          'recomenda uma comunicação preventiva aos órgãos parceiros.',
                'orientacao': 'Este recorte reúne o necessário para a decisão; os detalhes administrativos '
                              'permanecem com a divisão responsável.',
                'campos': [
                    ('Risco institucional', 'Moderado'),
                    ('Impacto externo', 'Não confirmado'),
                    ('Diretorias envolvidas', 'Monitoramento Ambiental e Assuntos Jurídicos'),
                ],
                'decisoes': [
                    ('Aprovar comunicação preventiva aos órgãos parceiros',
                     'Recomendação da divisão após a revisão do relatório de campo.',
                     D(2026, 11, 5), 'Pendente'),
                ],
                'historico': [
                    (D(2026, 11, 2), 'Síntese estratégica encaminhada ao gabinete do ministro.'),
                ],
            },
        },
    },
    {
        'codigo': 'DOS-2026-021',
        'titulo': 'Revisão de conformidade do Laboratório Beta',
        'situacao': 'Pendências em aberto',
        'divisao': 'Divisão de Conformidade e Fiscalização',
        'atualizado_em': D(2026, 10, 31),
        'recortes': {
            1: {
                'resumo': 'Revisão periódica de conformidade em andamento no Laboratório Beta. As rotinas '
                          'de acesso dos servidores permanecem inalteradas.',
                'orientacao': 'Mantenha seu cadastro biométrico atualizado para evitar a suspensão do acesso '
                              'durante a revisão.',
                'campos': [
                    ('Tipo de revisão', 'Periódica'),
                    ('Previsão de conclusão', '14/11/2026'),
                ],
                'historico': [
                    (D(2026, 10, 20), 'Revisão periódica iniciada.'),
                ],
            },
            2: {
                'resumo': 'A revisão identificou atrasos documentais e credenciais a renovar. Não há '
                          'incidente associado a este dossiê.',
                'orientacao': 'Priorize as renovações de credenciais com vencimento mais próximo.',
                'campos': [
                    ('Coordenação responsável', 'Coordenação de Conformidade'),
                    ('Escopo', 'Registros de acesso e inventário documental'),
                    ('Período auditado', '3º trimestre de 2026'),
                    ('Credenciais a renovar', '4 servidores'),
                ],
                'pendencias': [
                    ('Renovar as credenciais de acesso de quatro servidores',
                     'Solicitar novo cadastro biométrico ao administrador do sistema.',
                     D(2026, 11, 8), 'Aberta'),
                    ('Concluir a auditoria documental do 3º trimestre',
                     'Consolidar termos de responsabilidade e registros de acesso.',
                     D(2026, 11, 12), 'Aberta'),
                    ('Registrar a inspeção de rotina',
                     'Inspeção concluída sem não conformidades graves.', D(2026, 10, 28), 'Concluída'),
                ],
                'historico': [
                    (D(2026, 10, 20), 'Revisão aberta pela Divisão de Conformidade e Fiscalização.'),
                    (D(2026, 10, 28), 'Inspeção de rotina registrada.'),
                    (D(2026, 10, 31), 'Pendências documentais consolidadas.'),
                ],
            },
            3: {
                'resumo': 'Atrasos documentais pontuais, sem incidente associado e sem necessidade de '
                          'decisão ministerial neste momento.',
                'orientacao': 'O gabinete será acionado caso a auditoria identifique não conformidade grave.',
                'campos': [
                    ('Risco institucional', 'Baixo'),
                    ('Decisão ministerial', 'Não necessária no momento'),
                    ('Conclusão prevista', '14/11/2026'),
                ],
                'historico': [
                    (D(2026, 10, 31), 'Gabinete informado sobre o andamento da revisão.'),
                ],
            },
        },
    },
    {
        'codigo': 'DOS-2026-027',
        'titulo': 'Plano de resposta integrada da Bacia Gama',
        'situacao': 'Aguardando decisão',
        'divisao': 'Divisão de Emergências Ambientais',
        'atualizado_em': D(2026, 11, 1),
        'recortes': {
            2: {
                'resumo': 'Plano de resposta em consolidação com as equipes de plantão. A versão final '
                          'depende da validação das escalas e dos contatos.',
                'orientacao': 'Compartilhe o plano somente com as equipes designadas.',
                'campos': [
                    ('Coordenação responsável', 'Coordenação de Emergências Ambientais'),
                    ('Versão do plano', '0.9, em revisão'),
                    ('Equipes envolvidas', 'Plantão regional e Assessoria de Comunicação'),
                ],
                'pendencias': [
                    ('Validar a escala de plantão de novembro',
                     'Confirmar substitutos para feriados e fins de semana.', D(2026, 11, 3), 'Aberta'),
                    ('Atualizar a lista de contatos de emergência',
                     'Conferir telefones e responsáveis dos órgãos parceiros.', D(2026, 11, 4), 'Aberta'),
                    ('Revisar o fluxo de acionamento',
                     'Fluxo revisado com a Assessoria de Comunicação.', D(2026, 10, 29), 'Concluída'),
                ],
                'historico': [
                    (D(2026, 10, 25), 'Plano aberto pela Divisão de Emergências Ambientais.'),
                    (D(2026, 10, 29), 'Fluxo de acionamento revisado.'),
                    (D(2026, 11, 1), 'Versão 0.9 encaminhada para validação final.'),
                ],
            },
            3: {
                'resumo': 'O plano está pronto para aprovação, condicionado à definição do porta-voz e à '
                          'autorização de um exercício simulado com órgãos estaduais.',
                'orientacao': 'As decisões abaixo precisam ser deliberadas pelo ministro antes da publicação '
                              'da versão final.',
                'campos': [
                    ('Risco institucional', 'Moderado'),
                    ('Órgãos parceiros', 'Três secretarias estaduais'),
                    ('Publicação prevista', '12/11/2026'),
                ],
                'decisoes': [
                    ('Definir o porta-voz para comunicação de crise',
                     'Indicação necessária antes da publicação do plano.', D(2026, 11, 6), 'Pendente'),
                    ('Autorizar exercício simulado com órgãos estaduais',
                     'Exercício de mesa, sem mobilização de equipes em campo.', D(2026, 11, 10), 'Pendente'),
                ],
                'historico': [
                    (D(2026, 11, 1), 'Plano encaminhado ao gabinete para deliberação.'),
                ],
            },
        },
    },
    {
        'codigo': 'DOS-2026-031',
        'titulo': 'Avaliação anual da política de acesso ao cofre',
        'situacao': 'Reservado ao ministro',
        'divisao': 'Gabinete do Ministro',
        'atualizado_em': D(2026, 10, 29),
        'recortes': {
            3: {
                'resumo': 'Avaliação consolidada da política de níveis de acesso, com recomendações sobre '
                          'revisão de permissões, prazo das sessões e recadastro biométrico.',
                'orientacao': 'Documento de uso exclusivo do ministro. Os demais níveis não possuem recorte '
                              'deste dossiê.',
                'campos': [
                    ('Classificação', 'Exclusivo do nível 3'),
                    ('Período avaliado', 'Janeiro a outubro de 2026'),
                    ('Recomendações', '3'),
                ],
                'decisoes': [
                    ('Aprovar a revisão semestral das permissões',
                     'Revisar periodicamente os usuários ativos de cada nível.', D(2026, 11, 14), 'Pendente'),
                    ('Manter as sessões restritas a 15 minutos',
                     'Prazo atual considerado adequado pela avaliação.', D(2026, 10, 29), 'Registrada'),
                ],
                'historico': [
                    (D(2026, 10, 29), 'Avaliação concluída e entregue ao gabinete do ministro.'),
                ],
            },
        },
    },
]
