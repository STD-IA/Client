import json
from multiprocessing import shared_memory

class Memoria:
    def inicializar_memoria_compartilhada(self, data):
        data_json = json.dumps(data)
        memoria_compartilhada = shared_memory.SharedMemory(create=True, size=len(data_json))
        memoria_compartilhada.buf[:len(data_json)] = data_json.encode('utf-8')
        
        return memoria_compartilhada

    def ler_memoria_compartilhada(self, memoria_compartilhada):
        data_json = bytes(memoria_compartilhada.buf[:memoria_compartilhada.size]).decode('utf-8').rstrip('\x00')  # Remove dados residuais

        return json.loads(data_json)

    def escrever_memoria_compartilhada(self, memoria_compartilhada, data):
        data_json = json.dumps(data)
        if len(data_json) > memoria_compartilhada.size:
            raise ValueError("O tamanho do JSON excede o tamanho da memória compartilhada!")
        memoria_compartilhada.buf[:len(data_json)] = data_json.encode('utf-8')
        memoria_compartilhada.buf[len(data_json):] = b'\x00' * (memoria_compartilhada.size - len(data_json))  # Limpa o buffer residual