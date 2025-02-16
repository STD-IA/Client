import time
import configparser

from multiprocessing import Process, Manager
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer
from treinador import Treinar
from memoria_compartilhada import Memoria

"""
RequestHandler - Definir como o servidor XML-RPC lida com as requisições.
"""
class RequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ('/RPC2')

class Distribuidor:
    memoriaObj = Memoria()
    treinadorObj = Treinar()

    lock = 0
    
    task_memoria_comp = 0
    servidores_memoria_comp = 0
    
    def __init__(self):
        config = configparser.ConfigParser()
        config.read('config.ini')

        parametro = self.parametros(config)

        # Configura os argumentos para cada treinamento
        tasks = []
        for model_name in parametro['model_name']:
            for epoch in parametro['epoch']:
                for learning_rate in parametro['learning_rate']:
                    for weight_decay in parametro['weight_decay']:
                        tasks.append((model_name, epoch, learning_rate, weight_decay, parametro['replicacoes']))


        # Inicializar memória compartilhada para tasks
        self.task_memoria_comp = self.memoriaObj.inicializar_memoria_compartilhada(tasks)
        self.servidores_memoria_comp = self.memoriaObj.inicializar_memoria_compartilhada([("000.000.000.000", 0)] * len(tasks))
        self.memoriaObj.escrever_memoria_compartilhada(self.servidores_memoria_comp, [])

        #Lock compartilhado entre processos
        manager = Manager()
        self.lock = manager.Lock()

        ip = config.get('NameServer','IP')
        porta = config.getint('NameServer','Port')
        
        print(f"Iniciando servidor em {ip}:{porta}...")
        server = SimpleXMLRPCServer((ip, porta), requestHandler=RequestHandler)
        server.register_function(self.cadastrar_servidor)

        print("Servidor distribuidor inicializado.")
        self.treinadorObj.tempo_inicio = time.time()
        server.serve_forever()

    #Registra um servidor e inicia um processo de treinamento nele
    def cadastrar_servidor(self, ip, porta):
        server = (ip, porta)
        with self.lock:
            servidores = self.memoriaObj.ler_memoria_compartilhada(self.servidores_memoria_comp)
            try:
                servidores.append([ip,porta])
                self.memoriaObj.escrever_memoria_compartilhada(self.servidores_memoria_comp, servidores)
            except:
                return "Erro: Não é possível registrar mais servidores processadores."

        Process(target=self.treinadorObj.treinar,
                args=(server[0], 
                      server[1], 
                      self.task_memoria_comp.name, 
                      self.servidores_memoria_comp.name, 
                      self.lock)).start()
        
        return "Servidor registrado e inicializando o processo"

    def parametros(self, config):
        return {
            'replicacoes': config.getint('Params', 'replicacoes'),
            'model_name': [e for e in config['Params']['model_names'].split(', ')],
            'epoch': [int(e) for e in config['Params']['epochs'].split(', ')],
            'learning_rate': [float(e) for e in config['Params']['learning_rates'].split(', ')],
            'weight_decay': [float(e) for e in config['Params']['weight_decays'].split(', ')]  
        }

if __name__ == "__main__":
    Distribuidor()
