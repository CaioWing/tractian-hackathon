from openai import OpenAI
import PyPDF2
import os
import tiktoken
import numpy as np
import json
import asyncio
from typing import List, Dict
from pydantic import BaseModel

class SafetyStep(BaseModel):
    ordem: int
    descricao: str
    justificativa: str
    medidas_seguranca: List[str]
    duracao: str

class SafetySolution(BaseModel):
    passos: List[SafetyStep]
    equipamentos_necessarios: List[str]
    observacoes: List[str]
    referencias: List[str]

class SafetyResponse(BaseModel):
    problema: str
    solucao: SafetySolution

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extracts text from a PDF file."""
    text = ""
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            text += page.extract_text()
    return text

def split_text(text: str, max_tokens: int = 500) -> List[str]:
    """Splits text into chunks of a specified maximum number of tokens."""
    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = start + max_tokens
        chunk_tokens = tokens[start:end]
        chunk_text = encoding.decode(chunk_tokens)
        chunks.append(chunk_text)
        start = end
    return chunks

async def get_embeddings(texts: List[str], client: OpenAI) -> List[List[float]]:
    """Generates embeddings for a list of texts using the new OpenAI client."""
    embeddings = []
    batch_size = 1000
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.embeddings.create(
                input=batch,
                model="text-embedding-ada-002"
            )
        )
        embeddings.extend([data.embedding for data in response.data])
    return embeddings

def vector_search(query_embedding: List[float], embeddings: List[List[float]], top_k: int = 5) -> List[int]:
    """Performs a vector search to find the most similar embeddings."""
    embeddings = np.array(embeddings)
    query_embedding = np.array(query_embedding)
    similarities = np.dot(embeddings, query_embedding)
    top_k_indices = similarities.argsort()[-top_k:][::-1]
    return top_k_indices

async def process_pdf_with_assistant(pdf_path: str, problema: str, client: OpenAI) -> Dict:
    """Process PDF and generate response using the new OpenAI client."""
    # Step 1: Extract text from the PDF
    text = extract_text_from_pdf(pdf_path)
    
    # Step 2: Split the text into chunks
    chunks = split_text(text, max_tokens=500)
    
    # Step 3: Create embeddings for each chunk
    print("Creating embeddings for chunks...")
    chunk_embeddings = await get_embeddings(chunks, client)
    
    # Step 4: Create an embedding for the query/problem
    query_embedding_response = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: client.embeddings.create(
            input=problema,
            model="text-embedding-ada-002"
        )
    )
    query_embedding = query_embedding_response.data[0].embedding
    
    # Step 5: Retrieve relevant chunks using vector search
    top_k_indices = vector_search(query_embedding, chunk_embeddings, top_k=5)
    relevant_chunks = [chunks[i] for i in top_k_indices]
    
    # Step 6: Prepare the prompt for the assistant
    context = "\n\n".join(relevant_chunks)
    instructions = """
Você é um especialista em análise de normas técnicas e segurança.
Use o conteúdo dos documentos fornecidos para responder problemas específicos.
Suas respostas devem ser em português e estruturadas no seguinte formato JSON:
{
    "problema": "descrição do problema",
    "solucao": {
        "passos": [
            {
                "ordem": 1,
                "descricao": "descrição detalhada do passo",
                "justificativa": "baseado em qual parte da norma",
                "medidas_seguranca": ["lista de medidas de segurança"]
                "duracao": "20min"
            }
        ],
        "equipamentos_necessarios": ["lista de equipamentos necessários para realização dos serviços"],
        "observacoes": ["observações importantes"],
        "referencias": ["referências específicas da norma"]
    }
}
Mantenha suas respostas técnicas e precisas, fundamentadas no conteúdo do documento.
"""
    prompt = f"{instructions}\n\nContexto:\n{context}\n\nProblema: {problema}\nResposta:"
    
    # Step 7: Get the assistant's response using the new chat completion endpoint
    print("Generating assistant's response...")
    response = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: client.beta.chat.completions.parse(
            model="gpt-4o-mini-2024-07-18",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500,
            response_format=SafetyResponse,
        )
    )
    
    safety_response = response.choices[0].message.parsed
    
    # Save response to file
    output_filename = f"resposta_problema.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(safety_response.model_dump(), f, ensure_ascii=False, indent=4)
    print(f"\nResposta salva em: {output_filename}")
    
    return safety_response

async def main():
    # Initialize the OpenAI client
    client = OpenAI()  # Make sure OPENAI_API_KEY is set in your environment variables
    
    pdf_path = "prompts/nr-12-atualizada-2022-1.pdf"
    problema = """Bom dia Oswaldo, tudo certo? Passando para a gente alinhar as coisas que ficaram pendente para a gente fazer no domingo Ficaram alguns serviços que acabaram que a gente não conseguiu tocar durante a semana Mas
deixa eu explicar aqui para vocês algumas coisas que a gente tem que resolver logo, tá bom? Então conhecendo pela linha 3, eu preciso que façam a lubrificação dos rolamentos ali Essa máquina ali já está dando o
s sinais de desgaste já tem um certo tempo O pessoal reportou já barulho estranho nesse equipamento Então tem que botar o lubrificante correto, ele já está no estoque, aquele código lá, o azul 6624 Então já tom
a cuidado com isso, já faz essa lubrificação com essa máquina aí E não pode esquecer de conferir a ficha técnica dele para colocar a quantidade certa, tá? Da outra vez deu problema Então depois disso eu preciso
 também que vocês dêem uma verificada no nível de óleo lá da desencapadora, lá da linha 12 É um equipamento que do nada dá uns picos de temperatura lá, o pessoal já reportou, já mandou para a gerência Foi uma m
erda isso Então revisar mesmo as medições, ver se está tudo certo lá com o nível de óleo dela Porque se sair do óleo recompensado ela vai começar a esquentar e corre risco de parar e vai dar BO E também quem pr
ecisa dar uma olhada, lá no compressor 5 Aquele lá bem da central, o filtro de ar já passou do ponto Ele estava para ser trocado na última parada, mas ele acabou ficando para agora Então está bem crítico, então
 tem que fazer a substituição agora, agora no domingo já, não dá para esperar O filtro de novo eu já pechei, mandei o menino trazer lá do almoxarifado Está debaixo da bancada, só vocês pegarem e trocar também,
tá? E aproveita que você está no compressor, aproveita e dá um polinho lá naquela bomba de circulação Aquela lá do canto direito, o pessoal falou que ela estava fazendo barulho Aproveita e dá uma olhadinha lá p
ara mim, tá? Basicamente isso, qualquer coisa aí você não me avisa, tá? Porque eu estou de folga, segundamente resolve Valeu!"""
    
    try:
        resposta = await process_pdf_with_assistant(pdf_path, problema, client)
    except Exception as e:
        print(f"Erro ao processar PDF: {e}")

if __name__ == "__main__":
    asyncio.run(main())