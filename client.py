import json
import time
import socket
import logging
import configparser
import xmlrpc.client
from logging.handlers import RotatingFileHandler
from multiprocessing import Process, shared_memory, Manager
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer

inicio, shm_tasks, shm_servidores, lock = 0,0,0,0
log_file = "treinamento.log"

class RequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ('/RPC2')

def cadastrar_servidor(ip, porta):
    srv = (ip, porta)
    with lock:
        servidores = read_shared_memory(shm_servidores)
        try:
            servidores.append([ip,porta])
            write_shared_memory(shm_servidores, servidores)
        except:
            return "Erro: Não é possível registrar mais servidores."
    Process(target=treinar, args=(srv[0], srv[1], shm_tasks.name, shm_servidores.name, lock, log_file)).start()
    return "Server registered."

# Configurar logging
def configure_logging(log_file):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Rotating file handler para salvar logs em arquivo
    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=2)
    file_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(file_handler)

    # Console handler para exibir logs no terminal
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(console_handler)

    return logger

# Inicializar memória compartilhada
def initialize_shared_memory(data):
    data_json = json.dumps(data)
    shm = shared_memory.SharedMemory(create=True, size=len(data_json))
    shm.buf[:len(data_json)] = data_json.encode('utf-8')
    return shm

def read_shared_memory(shm):
    data_json = bytes(shm.buf[:shm.size]).decode('utf-8').rstrip('\x00')  # Remove dados residuais
    return json.loads(data_json)

def write_shared_memory(shm, data):
    data_json = json.dumps(data)
    if len(data_json) > shm.size:
        raise ValueError("O tamanho do JSON excede o tamanho da memória compartilhada!")
    shm.buf[:len(data_json)] = data_json.encode('utf-8')
    shm.buf[len(data_json):] = b'\x00' * (shm.size - len(data_json))  # Limpa o buffer residual

# Função de treinamento
def treinar(ip, porta, shm_tasks_name, shm_servidores_name, lock, log_file):
    logger = configure_logging(log_file)
    shm_tasks = shared_memory.SharedMemory(name=shm_tasks_name)
    shm_servidores = shared_memory.SharedMemory(name=shm_servidores_name)
    while True:
        with lock:
            tasks = read_shared_memory(shm_tasks)
            if not tasks:
                servidores = read_shared_memory(shm_servidores)
                servidores.remove([ip,porta])
                if not servidores:
                    fim = time.time()
                    duracao = fim - inicio
                    logger.info(f"Treinamento concluído. Duração: {duracao}s")
                    shm_tasks.close()
                    shm_tasks.unlink()
                    del shm_tasks
                    shm_servidores.close()
                    shm_servidores.unlink()
                    del shm_servidores
                    return
                write_shared_memory(shm_servidores, servidores)
                return
            task = tasks.pop(0)
            write_shared_memory(shm_tasks, tasks)
        # Chamar função de treinamento remota
        try:
            client = xmlrpc.client.ServerProxy(f"http://{ip}:{porta}")
            result = client.treinar(task[0], task[1], task[2], task[3], task[4])
            logger.info(f"Resultado do treinamento: {result}")
        except Exception as e:
            with lock:
                logger.error(f"Erro no servidor {ip}:{porta} durante o treinamento de {task}: {e}")
                servidores = read_shared_memory(shm_servidores)
                servidores.remove([ip,porta])
                write_shared_memory(shm_servidores, servidores)
                tasks = read_shared_memory(shm_tasks)
                tasks.insert(0,task)
                write_shared_memory(shm_tasks, tasks)
            return

if __name__ == "__main__":
    # Configuração de logging no processo principal
    logger = configure_logging(log_file)

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
    shm_tasks = initialize_shared_memory(tasks)
    servidores = [("000.000.000.000",0)]*len(tasks)
    shm_servidores = initialize_shared_memory(servidores)
    write_shared_memory(shm_servidores, [])

    # Criar um Lock compartilhado entre processos
    manager = Manager()
    lock = manager.Lock()

    # Obter IP e porta
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
