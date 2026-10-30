import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { LoginPage } from './login-page';

describe('LoginPage', () => {
  let component: LoginPage;
  let fixture: ComponentFixture<LoginPage>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LoginPage],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(LoginPage);
    component = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  });

  afterEach(() => http.verify());

  function preencherCredenciais(): void {
    for (const [campo, valor] of [['cpf', '52998224725'], ['senha', 'Senha-sintetica!']]) {
      const input = fixture.nativeElement.querySelector(`#${campo}`) as HTMLInputElement;
      input.value = valor;
      input.dispatchEvent(new Event('input'));
    }
  }

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('exibe o motivo da API sem substituir por uma mensagem genérica', async () => {
    preencherCredenciais();
    const envio = component.onSubmit();
    http.expectOne('http://localhost:8000/api/autenticacao/credenciais').flush(
      { detail: 'CPF ou senha inválidos.' }, { status: 401, statusText: 'Unauthorized' },
    );
    await envio;
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]').textContent)
      .toContain('CPF ou senha inválidos.');
    expect(fixture.nativeElement.querySelector('button').textContent).toContain('Continuar');
  });

  it('exibe os motivos de validação enviados no detail', async () => {
    preencherCredenciais();
    const envio = component.onSubmit();
    http.expectOne('http://localhost:8000/api/autenticacao/credenciais').flush(
      { detail: [{ loc: ['body', 'cpf'], msg: 'Dígitos verificadores do CPF inválidos.', type: 'value_error' }] },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    await envio;
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]').textContent)
      .toContain('Dígitos verificadores do CPF inválidos.');
  });

  it('orienta sobre conexão quando o serviço está indisponível', async () => {
    preencherCredenciais();
    const envio = component.onSubmit();
    http.expectOne('http://localhost:8000/api/autenticacao/credenciais')
      .error(new ProgressEvent('error'));
    await envio;
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]').textContent)
      .toContain('Não foi possível conectar ao serviço');
  });
});
