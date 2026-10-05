import { Component, OnInit } from '@angular/core';
import { UsuarioService } from '../services/usuario.service';
import { Usuario } from '../model/usuario/usuario.model';
import { ValidationError } from '../model/validation-error/validation-error.model';
import { UsuarioCadastro } from '../model/usuario/usuario-cadastro.model';
import { Credenciais } from '../model/autenticacao/autenticacao.model';
import { VerificacaoRequest } from '../model/autenticacao/verificacao.model';


@Component({
  selector: 'app-usuario',
  templateUrl: './usuario.component.html'
})
export class UsuarioComponent implements OnInit {
  usuarios: Usuario[] = [];
  errosValidacao: ValidationError[] = [];

  // 🔹 variáveis para cadastro
  cpf: string = '';
  nome: string = '';
  nivel: number = 1;

  // 🔹 variáveis para login
  loginCpf: string = '';
  senha: string = '';

  constructor(private usuarioService: UsuarioService) {}

  ngOnInit() {
    this.carregarUsuarios();
  }

  carregarUsuarios() {
    this.usuarioService.listarUsuarios().subscribe({
      next: (res) => this.usuarios = res,
      error: (err) => console.error('Erro ao listar usuários:', err)
    });
  }

  atualizarUsuario(id: number, dados: any) {
    this.usuarioService.atualizarUsuario(id, dados).subscribe({
      next: (res) => {
        console.log('Usuário atualizado:', res);
        this.carregarUsuarios();
      },
      error: (err) => {
        if (Array.isArray(err)) {
          this.errosValidacao = err;
        } else {
          console.error('Erro ao atualizar usuário:', err);
        }
      }
    });
  }

  excluirUsuario(id: number) {
    this.usuarioService.excluirUsuario(id).subscribe({
      next: () => {
        console.log('Usuário excluído com sucesso');
        this.carregarUsuarios();
      },
      error: (err) => {
        if (Array.isArray(err)) {
          this.errosValidacao = err;
        } else {
          console.error('Erro ao excluir usuário:', err);
        }
      }
    });
  }

  atualizarBiometria(id: number, frente: any[]) {
    this.usuarioService.atualizarBiometria(id, frente).subscribe({
      next: (res) => {
        console.log('Biometria atualizada com sucesso:', res);
        this.carregarUsuarios();
      },
      error: (err) => {
        if (Array.isArray(err)) {
          this.errosValidacao = err;
        } else {
          console.error('Erro ao atualizar biometria:', err);
        }
      }
    });
  }

  cadastrarUsuario() {
    const novoUsuario: UsuarioCadastro = {
      frames: [
        { largura: 100, altura: 100, y0_base64: '...base64...' }
      ],
      cpf: this.cpf,
      nome: this.nome,
      nivel: this.nivel
    };

    this.usuarioService.cadastrarUsuario(novoUsuario).subscribe({
      next: (res) => console.log('Usuário cadastrado com sucesso:', res),
      error: (err) => console.error('Erro ao cadastrar usuário:', err)
    });
  }

  login() {
    const credenciais: Credenciais = {
      cpf: this.loginCpf,
      senha: this.senha
    };

    this.usuarioService.autenticarUsuario(credenciais).subscribe({
      next: (res) => {
        console.log('Login realizado com sucesso:', res);
        // aqui você pode salvar token no localStorage e redirecionar
      },
      error: (err) => {
        if (Array.isArray(err)) {
          this.errosValidacao = err;
        } else {
          console.error('Erro ao autenticar usuário:', err);
        }
      }
    });
  }

  verificarBiometria() {
    const dados: VerificacaoRequest = {
        frames: [
        { largura: 160, altura: 120, rgb_base64: '...base64...' }
        ]
    };

    this.usuarioService.verificarBiometria(dados).subscribe({
        next: (res) => {
        console.log('Verificação realizada com sucesso:', res);
        },
        error: (err) => {
        if (Array.isArray(err)) {
            this.errosValidacao = err;
        } else {
            console.error('Erro ao verificar biometria:', err);
        }
        }
    });
    }

 consultarSessao() {
    this.usuarioService.obterSessao().subscribe({
        next: (res) => {
        console.log('Sessão atual:', res);
        },
        error: (err) => {
        console.error('Erro ao consultar sessão:', err);
        }
    });
    }

 logout() {
    this.usuarioService.sairSessao().subscribe({
        next: (res) => {
        console.log('Sessão encerrada com sucesso:', res);
        
        localStorage.removeItem('token'); 
        },
        error: (err) => {
        console.error('Erro ao encerrar sessão:', err);
        }
    });
    }

}
