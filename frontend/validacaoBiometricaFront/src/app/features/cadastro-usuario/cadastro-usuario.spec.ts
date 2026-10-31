import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { CadastroUsuario } from './cadastro-usuario';

describe('Mensagens do cadastro', () => {
  let fixture: ComponentFixture<CadastroUsuario>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CadastroUsuario],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();
    fixture = TestBed.createComponent(CadastroUsuario);
    http = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
    for (const [campo, valor] of [
      ['nome', 'Pessoa de teste'], ['cpf', '52998224725'], ['senha', 'Senha-sintetica!'],
    ]) {
      const input = fixture.nativeElement.querySelector(`#${campo}`) as HTMLInputElement;
      input.value = valor;
      input.dispatchEvent(new Event('input'));
    }
  });

  afterEach(() => http.verify());

  it('mostra o motivo específico do cadastro recusado', async () => {
    const envio = fixture.componentInstance.cadastrar();
    http.expectOne('http://localhost:8000/api/usuarios').flush(
      { detail: 'CPF já cadastrado.' }, { status: 409, statusText: 'Conflict' },
    );
    await envio;
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]').textContent)
      .toContain('CPF já cadastrado.');
  });

  it('mostra todos os motivos de validação da API', async () => {
    const envio = fixture.componentInstance.cadastrar();
    http.expectOne('http://localhost:8000/api/usuarios').flush({ detail: [
      { loc: ['body', 'cpf'], msg: 'Informe um CPF válido.', type: 'value_error' },
      { loc: ['body', 'nome'], msg: 'Informe o nome do usuário.', type: 'value_error' },
    ] }, { status: 422, statusText: 'Unprocessable Entity' });
    await envio;
    fixture.detectChanges();
    const mensagem = fixture.nativeElement.querySelector('[role="alert"]').textContent;
    expect(mensagem).toContain('Informe um CPF válido.');
    expect(mensagem).toContain('Informe o nome do usuário.');
  });
});
