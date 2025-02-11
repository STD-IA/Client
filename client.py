import json
import time
import socket
import logging
import configparser
import xmlrpc.client
from logging.handlers import RotatingFileHandler
from multiprocessing import Process, shared_memory, Manager
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer

inicio, task_memoria_comp, servidores_memoria_comp, lock = 0,0,0,0
log_file = "treinamento.log"

class RequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ('/RPC2')

def cadastrar_servidor(ip, porta):
    srv = (ip, porta)
    with lock:
        servidores = ler_memoria_compartilhada(servidores_memoria_comp)
        try:
            servidores.append([ip,porta])
            escrever_memoria_compartilhada(servidores_memoria_comp, servidores)
        except:
            return "Erro: Não é possível registrar mais servidores."
    Process(target=treinar, args=(srv[0], srv[1], task_memoria_comp.name, servidores_memoria_comp.name, lock, log_file)).start()
    return "Server registered."

def log_config(log_file):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=2)
    file_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(console_handler)

    return logger

def inicializar_memoria_compartilhada(data):
    data_json = json.dumps(data)
    shm = shared_memory.SharedMemory(create=True, size=len(data_json))
    shm.buf[:len(data_json)] = data_json.encode('utf-8')
    return shm

def ler_memoria_compartilhada(shm):
    data_json = bytes(shm.buf[:shm.size]).decode('utf-8').rstrip('\x00')  # Remove dados residuais
    return json.loads(data_json)

def escrever_memoria_compartilhada(shm, data):
    data_json = json.dumps(data)
    if len(data_json) > shm.size:
        raise ValueError("O tamanho do JSON excede o tamanho da memória compartilhada!")
    shm.buf[:len(data_json)] = data_json.encode('utf-8')
    shm.buf[len(data_json):] = b'\x00' * (shm.size - len(data_json))  # Limpa o buffer residual

def treinar(ip, porta, task_memoria_comp_name, servidores_memoria_comp_name, lock, log_file):
    logger = log_config(log_file)
    task_memoria_comp = shared_memory.SharedMemory(name=task_memoria_comp_name)
    servidores_memoria_comp = shared_memory.SharedMemory(name=servidores_memoria_comp_name)
    while True:
        with lock:
            tasks = ler_memoria_compartilhada(task_memoria_comp)
            if not tasks:
                servidores = ler_memoria_compartilhada(servidores_memoria_comp)
                servidores.remove([ip,porta])
                if not servidores:
                    fim = time.time()
                    duracao = fim - inicio
                    logger.info(f"Treinamento concluído. Duração: {duracao}s")
                    task_memoria_comp.close()
                    task_memoria_comp.unlink()
                    del task_memoria_comp
                    servidores_memoria_comp.close()
                    servidores_memoria_comp.unlink()
                    del servidores_memoria_comp
                    return
                escrever_memoria_compartilhada(servidores_memoria_comp, servidores)
                return
            task = tasks.pop(0)
            escrever_memoria_compartilhada(task_memoria_comp, tasks)

        try:
            client = xmlrpc.client.ServerProxy(f"http://{ip}:{porta}")
            result = client.treinar(task[0], task[1], task[2], task[3], task[4])
            logger.info(f"Resultado do treinamento: {result}")
        except Exception as e:
            with lock:
                logger.error(f"Erro no servidor {ip}:{porta} durante o treinamento de {task}: {e}")
                servidores = ler_memoria_compartilhada(servidores_memoria_comp)
                servidores.remove([ip,porta])
                escrever_memoria_compartilhada(servidores_memoria_comp, servidores)
                tasks = ler_memoria_compartilhada(task_memoria_comp)
                tasks.insert(0,task)
                escrever_memoria_compartilhada(task_memoria_comp, tasks)
            return

if __name__ == "__main__":
    # Configuração de logging no processo principal
    logger = log_config(log_file)

    # Obter parametros de treinamento do documento
    config = configparser.ConfigParser()
    config.read('config.ini')
    replicacoes = config.getint('Params','replicacoes')
    model_names = [e for e in config['Params']['model_names'].split(', ')]
    epochs = [int(e) for e in config['Params']['epochs'].split(', ')]
    learning_rates = [float(e) for e in config['Params']['learning_rates'].split(', ')]
    weight_decays = [float(e) for e in config['Params']['weight_decays'].split(', ')]

    # Configura os argumentos para cada treinamento
    tasks = [
        (model_name, epoch, learning_rate, weight_decay, replicacoes)
        for model_name in model_names for epoch in epochs for learning_rate in learning_rates for weight_decay in weight_decays
    ]

    # Inicializar memória compartilhada para tasks
    task_memoria_comp = inicializar_memoria_compartilhada(tasks)
    servidores = [("000.000.000.000",0)]*len(tasks)
    servidores_memoria_comp = inicializar_memoria_compartilhada(servidores)
    escrever_memoria_compartilhada(servidores_memoria_comp, [])

    #Lock compartilhado entre processos
    manager = Manager()
    lock = manager.Lock()

    config.read('nsConfig.ini')
    ip = config.get('NameServer','IP')

    if(ip == 'auto'):
        ip = socket.gethostbyname(socket.gethostname())

    porta = config.getint('NameServer','Port')
    print(f"Iniciando servidor em {ip}:{porta}...")
    server = SimpleXMLRPCServer((ip, porta), requestHandler=RequestHandler)
    server.register_function(cadastrar_servidor)
    print("Servidor iniciado.")
    inicio = time.time()
    server.serve_forever()
