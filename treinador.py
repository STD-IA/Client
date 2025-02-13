import logging
import time
import xmlrpc.client

from multiprocessing import shared_memory
from logging.handlers import RotatingFileHandler
from memoria_compartilhada import Memoria

class Treinar:
    tempo_inicio = 0
    log_excessoes_file = "excessoes.log"
    log_avisos_file = "avisos.log"

    memoriaObj = Memoria()

    def __init__(self):
        pass

    def treinar(self, ip, porta, task_memoria_comp_name, servidores_memoria_comp_name, lock, log_file):
        logger_excessao = self.log_config(self.logger_excessao)
        logger_aviso = self.log_config(self.log_avisos_file)

        task_memoria_comp = shared_memory.SharedMemory(name=task_memoria_comp_name)
        servidores_memoria_comp = shared_memory.SharedMemory(name=servidores_memoria_comp_name)

        while True:
            with lock:
                tasks = self.memoriaObj.ler_memoria_compartilhada(task_memoria_comp)
                if not tasks:
                    servidores = self.memoriaObj.ler_memoria_compartilhada(servidores_memoria_comp)
                    servidores.remove([ip,porta])

                    if not servidores:
                        fim = time.time()
                        duracao = fim - self.tempo_inicio

                        logger_aviso.info(f"Treinamento concluído. Duração: {duracao}s")

                        task_memoria_comp.close()
                        task_memoria_comp.unlink()
                        del task_memoria_comp

                        servidores_memoria_comp.close()
                        servidores_memoria_comp.unlink()
                        del servidores_memoria_comp
                        return
                    self.memoriaObj.escrever_memoria_compartilhada(servidores_memoria_comp, servidores)
                    return
                
                task = tasks.pop(0)
                self.memoriaObj.escrever_memoria_compartilhada(task_memoria_comp, tasks)

            try:
                client = xmlrpc.client.ServerProxy(f"http://{ip}:{porta}")
                result = client.treinar(task[0], task[1], task[2], task[3], task[4])
                logger_aviso.info(f"Resultado do treinamento: {result}")

            except Exception as e:
                with lock:
                    logger_excessao.error(f"Erro no servidor {ip}:{porta} durante o treinamento de {task}: {e}")
                    servidores = self.memoriaObj.ler_memoria_compartilhada(servidores_memoria_comp)
                    servidores.remove([ip,porta])

                    self.memoriaObj.escrever_memoria_compartilhada(servidores_memoria_comp, servidores)
                    tasks = self.memoriaObj.ler_memoria_compartilhada(task_memoria_comp)
                    tasks.insert(0,task)
                    
                    self.memoriaObj.escrever_memoria_compartilhada(task_memoria_comp, tasks)
                return
        
    def log_config(self, log_file):
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)

        file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=2)
        file_handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(console_handler)

        return logger