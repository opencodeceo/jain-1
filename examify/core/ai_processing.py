import docx
from django.conf import settings
from openai import OpenAI as OpenAIClient
import google.generativeai as genai
import fitz # PyMuPDF
from google.cloud import aiplatform
# MatchingEngineIndexEndpoint is used for querying
# MatchingEngineIndex is used for upserting/managing the index itself
from google.cloud.aiplatform.matching_engine import MatchingEngineIndexEndpoint
import uuid
from .models import DocumentChunk
import logging

# Configure a logger for this module
logger = logging.getLogger(__name__)

# Placeholder for actual text splitting logic
def split_text_into_chunks(text, chunk_size=1000, chunk_overlap=200):
    words = text.split()
    chunks = []
    current_chunk_words = []
    current_length = 0

    for word in words:
        word_len = len(word)
        potential_new_length = current_length + word_len + (1 if current_chunk_words else 0)

        if potential_new_length > chunk_size and current_chunk_words:
            chunks.append(" ".join(current_chunk_words))

            if chunk_overlap > 0 and chunk_size > 0:
                overlap_word_count = 0
                temp_overlap_len = 0
                for i in range(len(current_chunk_words) - 1, -1, -1):
                    w = current_chunk_words[i]
                    if temp_overlap_len + len(w) + (1 if overlap_word_count > 0 else 0) <= chunk_overlap:
                        temp_overlap_len += len(w) + (1 if overlap_word_count > 0 else 0)
                        overlap_word_count += 1
                    else:
                        break
                current_chunk_words = current_chunk_words[len(current_chunk_words) - overlap_word_count:]
            else:
                current_chunk_words = []

            current_length = sum(len(w) for w in current_chunk_words) + (len(current_chunk_words) -1 if current_chunk_words else 0)

        current_chunk_words.append(word)
        current_length += word_len + (1 if len(current_chunk_words) > 1 else 0)

    if current_chunk_words:
        chunks.append(" ".join(current_chunk_words))

    return [chunk for chunk in chunks if chunk.strip()]


def extract_text_from_file(file_path, file_type):
    text = ""
    try:
        if file_type == 'pdf':
            with fitz.open(file_path) as doc:
                for page_num, page in enumerate(doc):
                    text += page.get_text()
            logger.info(f"Successfully extracted text from PDF: {file_path}")
        elif file_type == 'docx':
            doc_obj = docx.Document(file_path)
            for para in doc_obj.paragraphs:
                text += para.text + "\n"
            logger.info(f"Successfully extracted text from DOCX: {file_path}")
        else:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            logger.info(f"Attempted to extract text from unknown/text file: {file_path}")
    except Exception as e:
        logger.error(f"Error extracting text from {file_path} (type: {file_type}): {e}", exc_info=True)
    return text

# --- Embedding Generation ---
def get_embedding_provider():
    return settings.PREFERRED_EMBEDDING_PROVIDER

def get_google_embedding(text_chunk, task_type="RETRIEVAL_DOCUMENT"):
    if settings.GOOGLE_API_KEY == "YOUR_GOOGLE_API_KEY" or not settings.GOOGLE_API_KEY:
        logger.error("Google API Key is not configured (still placeholder or empty). Cannot generate Google embedding.")
        return None
    genai.configure(api_key=settings.GOOGLE_API_KEY)
    try:
        result = genai.embed_content(
            model="models/embedding-001",
            content=text_chunk,
            task_type=task_type,
        )
        logger.debug(f"Successfully generated Google embedding for chunk: {text_chunk[:50]}...")
        return result['embedding']
    except Exception as e:
        logger.error(f"Error generating Google embedding for chunk '{text_chunk[:50]}...': {e}", exc_info=True)
        return None

def get_openai_embedding(text_chunk):
    if settings.OPENAI_API_KEY == "YOUR_OPENAI_API_KEY" or not settings.OPENAI_API_KEY:
        logger.error("OpenAI API Key is not configured (still placeholder or empty). Cannot generate OpenAI embedding.")
        return None
    try:
        client = OpenAIClient(api_key=settings.OPENAI_API_KEY)
        response = client.embeddings.create(
            input=text_chunk,
            model="text-embedding-ada-002"
        )
        logger.debug(f"Successfully generated OpenAI embedding for chunk: {text_chunk[:50]}...")
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Error generating OpenAI embedding for chunk '{text_chunk[:50]}...': {e}", exc_info=True)
        return None

def generate_embeddings(text_chunks):
    embeddings = []
    provider = get_embedding_provider()
    if not text_chunks:
        return embeddings

    for chunk_text in text_chunks: # Renamed 'chunk' to 'chunk_text' for clarity
        if not chunk_text.strip():
            logger.warning("Skipping empty chunk in generate_embeddings.")
            continue
        embedding = None
        if provider == 'google':
            embedding = get_google_embedding(chunk_text)
        elif provider == 'openai':
            embedding = get_openai_embedding(chunk_text)
        else:
            logger.error(f"Invalid embedding provider configured: {provider}")
            continue # Skip this chunk

        if embedding:
            embeddings.append(embedding)
        else:
            logger.warning(f"Skipping chunk due to embedding error in generate_embeddings: {chunk_text[:100]}...")
    return embeddings

# --- Vertex AI Vector Search Interaction ---
def get_vertex_ai_index_endpoint_object():
    if not all([
        settings.GOOGLE_CLOUD_PROJECT,
        settings.GOOGLE_CLOUD_REGION,
        settings.VERTEX_AI_INDEX_ENDPOINT_ID]) or \
        settings.VERTEX_AI_INDEX_ENDPOINT_ID == "YOUR_VERTEX_AI_INDEX_ENDPOINT_ID":
        logger.error("Vertex AI settings (project, region, index endpoint ID) are not fully configured or are placeholders.")
        return None

    try:
        # Initialize aiplatform if not already (idempotent for subsequent calls with same params)
        aiplatform.init(project=settings.GOOGLE_CLOUD_PROJECT, location=settings.GOOGLE_CLOUD_REGION)
        index_endpoint = MatchingEngineIndexEndpoint(index_endpoint_name=settings.VERTEX_AI_INDEX_ENDPOINT_ID)
        logger.info(f"Successfully initialized Vertex AI Index Endpoint object: {settings.VERTEX_AI_INDEX_ENDPOINT_ID}")
        return index_endpoint
    except Exception as e:
        logger.error(f"Error initializing Vertex AI Index Endpoint object '{settings.VERTEX_AI_INDEX_ENDPOINT_ID}': {e}", exc_info=True)
        return None

def upsert_chunks_to_vertex_ai(document_chunks_with_embeddings):
    if not settings.VERTEX_AI_INDEX_ID or settings.VERTEX_AI_INDEX_ID == "YOUR_VERTEX_AI_INDEX_ID":
        logger.error("Vertex AI Index ID is not configured or is a placeholder. Aborting upsert.")
        return False

    if not all([settings.GOOGLE_CLOUD_PROJECT, settings.GOOGLE_CLOUD_REGION]):
        logger.error("Google Cloud Project or Region not configured for Vertex AI upsert.")
        return False

    try:
        aiplatform.init(project=settings.GOOGLE_CLOUD_PROJECT, location=settings.GOOGLE_CLOUD_REGION)
        vertex_index = aiplatform.MatchingEngineIndex(index_name=settings.VERTEX_AI_INDEX_ID)

        datapoints = []
        for chunk_data in document_chunks_with_embeddings:
            if not ('id' in chunk_data and 'embedding' in chunk_data and chunk_data['embedding'] is not None):
                logger.warning(f"Skipping chunk in upsert due to missing 'id', 'embedding', or None embedding: ID {chunk_data.get('id', 'N/A')}")
                continue
            datapoints.append({'id': str(chunk_data['id']), 'embedding': chunk_data['embedding']})

        if not datapoints:
            logger.warning("No valid datapoints to upsert to Vertex AI.")
            return False

        logger.info(f"Upserting {len(datapoints)} datapoints to Vertex AI Index ID: {settings.VERTEX_AI_INDEX_ID}...")
        vertex_index.upsert_datapoints(datapoints=datapoints)
        logger.info(f"Successfully upserted {len(datapoints)} datapoints to Vertex AI.")
        return True

    except Exception as e:
        logger.error(f"Error upserting datapoints to Vertex AI Index '{settings.VERTEX_AI_INDEX_ID}': {e}", exc_info=True)
    return False

def process_study_material_file(study_material_instance):
    if not study_material_instance.file:
        logger.warning(f"No file associated with StudyMaterial ID {study_material_instance.id}")
        return

    file_path = study_material_instance.file.path
    file_name = study_material_instance.file.name
    file_type = file_name.split('.')[-1].lower() if '.' in file_name else ''

    logger.info(f"Processing {file_type} file: {file_path} for StudyMaterial ID {study_material_instance.id}")
    text_content = extract_text_from_file(file_path, file_type)
    if not text_content or not text_content.strip():
        logger.warning(f"No text content extracted for StudyMaterial ID {study_material_instance.id}.")
        return

    chunks_text_only = split_text_into_chunks(text_content)
    if not chunks_text_only:
        logger.warning(f"Text content could not be split into chunks for StudyMaterial ID {study_material_instance.id}.")
        return

    logger.info(f"Split '{file_name}' into {len(chunks_text_only)} chunks for StudyMaterial ID {study_material_instance.id}.")

    processed_chunks_for_vertex = []
    embedding_provider_name = get_embedding_provider()

    if embedding_provider_name == 'google' and (settings.GOOGLE_API_KEY == "YOUR_GOOGLE_API_KEY" or not settings.GOOGLE_API_KEY):
        logger.error(f"Google API Key not configured. Cannot process StudyMaterial ID {study_material_instance.id} with Google provider.")
        return
    if embedding_provider_name == 'openai' and (settings.OPENAI_API_KEY == "YOUR_OPENAI_API_KEY" or not settings.OPENAI_API_KEY):
        logger.error(f"OpenAI API Key not configured. Cannot process StudyMaterial ID {study_material_instance.id} with OpenAI provider.")
        return

    for i, chunk_text in enumerate(chunks_text_only):
        chunk_vector_id = str(uuid.uuid4())
        logger.info(f"Generating embedding for chunk {i+1}/{len(chunks_text_only)} of '{file_name}' (vector_id: {chunk_vector_id}) using {embedding_provider_name}...")
        embedding = None
        if embedding_provider_name == 'google':
            embedding = get_google_embedding(chunk_text)
        elif embedding_provider_name == 'openai':
            embedding = get_openai_embedding(chunk_text)

        if embedding:
            try:
                dc_instance = DocumentChunk.objects.create( # Capture instance for logging
                    study_material=study_material_instance,
                    chunk_text=chunk_text,
                    vector_id=chunk_vector_id,
                    embedding_provider=embedding_provider_name,
                    chunk_sequence_number=i
                )
                logger.debug(f"Saved DocumentChunk {dc_instance.id} with vector_id {chunk_vector_id} for StudyMaterial {study_material_instance.id}")
                processed_chunks_for_vertex.append({
                    'id': chunk_vector_id,
                    'embedding': embedding,
                    'study_material_id': study_material_instance.id
                })
            except Exception as e:
                 logger.error(f"Error saving DocumentChunk for SM_ID {study_material_instance.id}, chunk_seq {i}, vector_id {chunk_vector_id}: {e}", exc_info=True)
                 continue
        else:
            logger.warning(f"Failed to generate embedding for chunk {i+1} of StudyMaterial ID {study_material_instance.id}.")

    if not processed_chunks_for_vertex:
        logger.warning(f"No embeddings were successfully generated and saved for StudyMaterial ID {study_material_instance.id}. Nothing to upsert to Vertex AI.")
        return

    logger.info(f"Attempting to upsert {len(processed_chunks_for_vertex)} processed chunks to Vertex AI for StudyMaterial ID {study_material_instance.id}...")
    success = upsert_chunks_to_vertex_ai(processed_chunks_for_vertex)

    if success:
        logger.info(f"Successfully processed and upserted chunks for StudyMaterial ID {study_material_instance.id}.")
    else:
        logger.error(f"Failed to upsert chunks to Vertex AI for StudyMaterial ID {study_material_instance.id}.")
        logger.warning("Consider implementing rollback for Django DocumentChunk entries if Vertex AI upsert fails.")

# --- RAG Query Service ---

def query_vertex_ai_vector_search(query_embedding, top_k=5):
    index_endpoint_obj = get_vertex_ai_index_endpoint_object()
    if not index_endpoint_obj:
        logger.warning("Failed to get Vertex AI Index Endpoint for querying. Cannot proceed with vector search.")
        return []

    try:
        response = index_endpoint_obj.find_neighbors(
            queries=[query_embedding],
            num_neighbors=top_k,
        )
        logger.info(f"Vertex AI find_neighbors raw response: {response}") # Log raw response for inspection

        if response and response[0]:
            neighbor_ids_distances = [(neighbor.id, neighbor.distance) for neighbor in response[0]]
            logger.info(f"Found {len(neighbor_ids_distances)} neighbors in Vertex AI: {neighbor_ids_distances}")
            return neighbor_ids_distances
        else:
            logger.info("No neighbors found in Vertex AI for the query embedding.")
            return []
    except Exception as e:
        logger.error(f"Error querying Vertex AI Vector Search: {e}", exc_info=True)
        return []

def get_llm_response(prompt_text, provider=None, task_type='general_query'): # Added task_type, provider default None
    """
    Gets a response from the specified LLM provider, potentially tailoring by task_type.
    `prompt_text` here is the fully formed prompt including user query and context if RAG.
    For other tasks, it's the specific instruction and content.
    """
    if provider is None:
        provider = getattr(settings, 'PREFERRED_LLM_PROVIDER', 'google')

    logger.info(f"Getting LLM response using provider: {provider} for task: {task_type}")

    if provider == 'google':
        if settings.GOOGLE_API_KEY == "YOUR_GOOGLE_API_KEY" or not settings.GOOGLE_API_KEY:
            logger.error("Google API Key not configured for LLM.")
            return "Error: Google API Key not configured."
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        try:
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(prompt_text) # Pass the pre-formatted prompt

            gemini_response_text = ""
            if hasattr(response, 'text') and response.text:
                gemini_response_text = response.text
            elif hasattr(response, 'parts') and response.parts:
                gemini_response_text = "".join(part.text for part in response.parts if hasattr(part, 'text'))
            elif hasattr(response, 'candidates') and response.candidates and \
                 hasattr(response.candidates[0], 'content') and hasattr(response.candidates[0].content, 'parts'):
                candidate_parts = response.candidates[0].content.parts
                gemini_response_text = "".join(part.text for part in candidate_parts if hasattr(part, 'text'))

            if not gemini_response_text.strip(): # Removed 'and response' as it's always true if no exception
                logger.warning(f"Gemini response was empty or structure not as expected for task {task_type}. Raw response: {response}")
                return "Error: Could not parse Gemini response or response was empty."
            logger.debug(f"Successfully received response from Google Gemini for task {task_type}.")
            return gemini_response_text.strip()
        except Exception as e:
            logger.error(f"Error getting response from Google Gemini for task {task_type}: {e}", exc_info=True)
            return f"Error communicating with Google Gemini: {e}"

    elif provider == 'openai':
        if settings.OPENAI_API_KEY == "YOUR_OPENAI_API_KEY" or not settings.OPENAI_API_KEY:
            logger.error("OpenAI API Key not configured for LLM.")
            return "Error: OpenAI API Key not configured."
        try:
            client = OpenAIClient(api_key=settings.OPENAI_API_KEY)

            system_message = f"You are an AI assistant performing a {task_type} task."
            if task_type == 'summarize':
                 system_message = "You are an AI assistant skilled in summarizing texts concisely."
            elif task_type == 'explain_complex':
                 system_message = "You are an AI assistant skilled in explaining complex topics clearly and step-by-step."
            elif task_type == 'generate_questions':
                 system_message = "You are an AI assistant skilled in generating relevant exam questions from a given text."
            elif task_type == 'rag_query': # Specific system message for RAG
                 system_message = "You are an AI assistant answering questions based on provided context."


            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt_text}
            ]

            chat_completion = client.chat.completions.create(
                messages=messages,
                model="gpt-3.5-turbo",
            )
            response_text = chat_completion.choices[0].message.content
            logger.debug(f"Successfully received response from OpenAI for task {task_type}.")
            return response_text.strip()
        except Exception as e:
            logger.error(f"Error getting response from OpenAI for task {task_type}: {e}", exc_info=True)
            return f"Error communicating with OpenAI: {e}"
    else:
        logger.error(f"Invalid LLM provider specified: {provider}")
        return "Error: Invalid LLM provider specified."


def perform_rag_query(user_query):
    logger.info(f"Performing RAG query for: '{user_query[:100]}...'")
    embedding_provider = get_embedding_provider()
    query_embedding = None

    logger.info(f"Generating query embedding using {embedding_provider} for query: '{user_query}'") # Duplicated log, but ok
    if embedding_provider == 'google':
        query_embedding = get_google_embedding(user_query, task_type="RETRIEVAL_QUERY")
    elif embedding_provider == 'openai':
        query_embedding = get_openai_embedding(user_query)

    if not query_embedding:
        logger.error(f"Failed to generate query embedding for query: '{user_query}'. Cannot proceed with RAG.")
        return {"answer": None, "context_vector_ids": [], "error": "Error: Could not generate query embedding. Check API keys and provider settings."}

    logger.info("Querying Vertex AI Vector Search...")
    neighbor_ids_distances = query_vertex_ai_vector_search(query_embedding, top_k=3)

    vector_ids_of_retrieved_chunks = [item[0] for item in neighbor_ids_distances] # Get all potential vector_ids early

    if not neighbor_ids_distances:
        logger.info(f"No relevant document chunks found in Vertex AI for query: '{user_query}'.")
        return {"answer": "Could not find relevant information for your query.", "context_vector_ids": [], "error": None}

    retrieved_chunk_texts = []
    try:
        chunks_from_db = DocumentChunk.objects.filter(vector_id__in=vector_ids_of_retrieved_chunks)
        chunk_map = {str(chunk.vector_id): chunk.chunk_text for chunk in chunks_from_db}

        for vec_id, distance in neighbor_ids_distances:
            if vec_id in chunk_map:
                retrieved_chunk_texts.append(chunk_map[vec_id])
                logger.debug(f"Retrieved chunk (vector_id: {vec_id}, distance: {distance:.4f}): {chunk_map[vec_id][:100]}...")
            else:
                logger.warning(f"DocumentChunk with vector_id {vec_id} not found in Django DB, but was returned by Vertex AI.")
    except Exception as e:
        logger.error(f"Error retrieving document chunks from Django DB for query '{user_query}': {e}", exc_info=True)
        return {"answer": None, "context_vector_ids": vector_ids_of_retrieved_chunks, "error": "Error: Could not retrieve context information from database."}

    if not retrieved_chunk_texts:
        logger.warning(f"Found relevant information pointers in Vertex AI, but could not retrieve the content from Django DB for query: '{user_query}'.")
        return {"answer": "Found relevant information pointers, but could not retrieve the content from the database.",
                "context_vector_ids": vector_ids_of_retrieved_chunks, "error": "Content retrieval error."}

    context_str = "\n\n---\n\n".join(retrieved_chunk_texts)
    prompt = f"""Answer the following question based on the provided context.
Question: {user_query}

Context:
{context_str}

Answer:"""

    llm_provider_to_use = getattr(settings, 'PREFERRED_LLM_PROVIDER', embedding_provider)
    logger.info(f"Sending prompt to LLM provider: {llm_provider_to_use} for RAG query: '{user_query}'") # Updated log
    answer_text = get_llm_response(prompt, provider=llm_provider_to_use, task_type='rag_query')

    if isinstance(answer_text, str) and answer_text.startswith("Error:"):
        logger.error(f"LLM failed to provide an answer for RAG query '{user_query}': {answer_text}")
        return {"answer": None, "context_vector_ids": vector_ids_of_retrieved_chunks, "error": answer_text}

    logger.info(f"Received answer from LLM for RAG query: '{user_query}'. Answer: {answer_text[:100]}...")
    return {"answer": answer_text, "context_vector_ids": vector_ids_of_retrieved_chunks, "error": None}

# Conceptual placeholders for signal or model method integration
# ... (as before)


def grade_answer_with_ai(question_text, question_type, user_answer_text, question_points, options=None, context_text=None):
    if not user_answer_text or not user_answer_text.strip():
        logger.info(f"AI Grading: No answer provided for Q='{question_text[:30]}...'")
        return {
            'feedback': "No answer provided by the user.",
            'points_awarded': 0.0
        }

    llm_provider = getattr(settings, 'PREFERRED_LLM_PROVIDER', 'google')
    logger.info(f"AI Grading: Q='{question_text[:50]}...' A='{user_answer_text[:50]}...' using {llm_provider}. Points: {question_points}")

    prompt_parts = [
        f"You are an AI grading assistant. Evaluate the user's answer for the following question.",
        f"Question: {question_text}",
    ]

    options_text_for_prompt = ""
    if question_type == 'multiple_choice' and options and isinstance(options, dict):
        formatted_options = []
        for key, value in options.items():
            if key.lower() not in ['correct', 'options_text', 'explanation']:
                formatted_options.append(f"{key}) {value}")
        if formatted_options:
            options_text_for_prompt = " ".join(formatted_options)
            prompt_parts.append(f"Options provided to user: {options_text_for_prompt}")
        prompt_parts.append(f"User's Answer/Selected Option: '{user_answer_text}'")

    elif question_type in ['short_answer', 'essay']:
        prompt_parts.append(f"User's Answer: {user_answer_text}")

    if context_text:
        prompt_parts.append(f"Relevant Context from Study Material (use this to validate the answer if applicable): {context_text}")

    prompt_parts.append(f"The question is worth {question_points} points.")

    if question_type in ['short_answer', 'essay']:
        prompt_parts.append(
            f"Provide constructive feedback on the user's answer. "
            f"Then, on a new line, strictly output 'Awarded Points: X' where X is the number of points awarded out of {question_points}. "
            f"X should be an integer or a float (e.g., Awarded Points: {float(question_points)/2.0}). Base your grading on accuracy, completeness, and relevance to the question and provided context (if any)."
        )
    else:
         prompt_parts.append(
            f"Provide a brief explanation for why the user's selection might be correct or incorrect, or offer additional insights related to the question and options. "
            f"Do not award points for multiple-choice questions in your response."
         )

    prompt = "\n\n".join(prompt_parts)
    logger.debug(f"AI Grading Prompt for Q='{question_text[:50]}...':\n{prompt}")

    # For AI grading, the task_type is specific
    raw_llm_response = get_llm_response(prompt, provider=llm_provider, task_type='grade_answer')

    if raw_llm_response is None or (isinstance(raw_llm_response, str) and raw_llm_response.startswith("Error:")):
        logger.error(f"LLM error during AI grading for Q='{question_text[:50]}...': {raw_llm_response}")
        return {
            'feedback': f"Automated grading failed due to an AI service error: {raw_llm_response}",
            'points_awarded': 0.0
        }

    feedback_parts = []
    awarded_points_value = 0.0
    parsed_points_successfully = False

    lines = raw_llm_response.splitlines()
    for line in lines:
        normalized_line = line.lower().strip()
        if normalized_line.startswith("awarded points:"):
            try:
                points_str = normalized_line.replace("awarded points:", "").strip()
                awarded_points_value = float(points_str)
                awarded_points_value = min(max(0.0, awarded_points_value), float(question_points))
                parsed_points_successfully = True
                logger.info(f"AI Grading: Parsed points '{awarded_points_value}' from LLM line: '{line}'")
            except ValueError:
                logger.warning(f"AI Grading: Could not parse points from LLM line: '{line}' for Q='{question_text[:50]}...'")
        else:
            feedback_parts.append(line)

    final_feedback = "\n".join(feedback_parts).strip()
    if not final_feedback :
        if question_type in ['short_answer', 'essay'] and parsed_points_successfully:
             final_feedback = "Grading complete. Please review the awarded points."
        elif question_type == 'multiple_choice':
             final_feedback = "Feedback for your choice."
        else:
             final_feedback = "AI feedback could not be fully parsed or was not provided."

        if not parsed_points_successfully and question_type in ['short_answer', 'essay']:
             final_feedback += " Points could not be determined by AI."

    points_to_return = awarded_points_value if question_type in ['short_answer', 'essay'] and parsed_points_successfully else None

    logger.info(f"AI Grading result for Q='{question_text[:50]}...' - Feedback: '{final_feedback[:50]}...', Points from AI: {points_to_return}")
    return {
        'feedback': final_feedback,
        'points_awarded': points_to_return
    }

# New function for summarization
def summarize_text_with_llm(text_to_summarize, provider=None):
    if not text_to_summarize or not text_to_summarize.strip():
        logger.warning("Summarization called with empty text.")
        return "Error: No text provided for summarization."

    prompt = f"Please provide a concise summary of the following text:\n\n---\n{text_to_summarize}\n---"

    summary = get_llm_response(prompt, provider=provider, task_type='summarize')
    return summary


# --- OCR Function ---
from google.cloud import vision # Import the vision client

def extract_text_from_image_gcp(image_content_bytes):
    """
    Extracts text from an image using Google Cloud Vision API.
    Args:
        image_content_bytes: The byte content of the image.
    Returns:
        The extracted text string, or None if an error occurs, or an empty string if no text is found.
    """
    # The check for GOOGLE_API_KEY might be misleading for Vision API if using ADC.
    # Vision client typically relies on GOOGLE_APPLICATION_CREDENTIALS env var or ADC.
    # Explicitly setting GOOGLE_API_KEY is not standard for Vision client library.
    # We'll rely on the standard auth flow (e.g., ADC) and handle potential auth errors in try-except.
    logger.info("Attempting to extract text from image using Google Cloud Vision API.")

    try:
        client_options = {}
        # Example if a regional endpoint is needed, though often not required for Vision API basic use.
        # if hasattr(settings, 'GOOGLE_CLOUD_VISION_API_ENDPOINT') and settings.GOOGLE_CLOUD_VISION_API_ENDPOINT:
        #      client_options['api_endpoint'] = settings.GOOGLE_CLOUD_VISION_API_ENDPOINT

        client = vision.ImageAnnotatorClient(**client_options)

        image = vision.Image(content=image_content_bytes)

        # Using document_text_detection for potentially dense text in educational materials
        response = client.document_text_detection(image=image)
        # Alternatively, for sparser text: response = client.text_detection(image=image)

        if response.error.message:
            logger.error(f"Google Cloud Vision API error: {response.error.message}")
            return None # Indicates an API-level error

        if response.full_text_annotation and response.full_text_annotation.text:
            extracted_text = response.full_text_annotation.text
            logger.info(f"Successfully extracted text (length: {len(extracted_text)}) from image using Google Cloud Vision API.")
            return extracted_text
        else:
            logger.info("No text found in image by Google Cloud Vision API.")
            return "" # Return empty string if no text detected, distinct from an error

    except Exception as e:
        logger.error(f"Error during Google Cloud Vision API call: {e}", exc_info=True)
        return None # Indicates a client-side or communication error


# --- New Service Function for Complex Problem Explanation ---
def explain_complex_problem_with_llm(user_query, context_text=None, provider=None):
    """
    Uses an LLM to provide a detailed, step-by-step explanation for a complex query.
    Optionally uses provided context_text.
    """
    if not user_query or not user_query.strip():
        logger.warning("Explain complex problem called with empty query.")
        return "Error: No query provided for explanation."

    prompt_parts = [
        f"Please provide a detailed, step-by-step explanation for the following query or problem.",
        f"Query/Problem: {user_query}"
    ]
    if context_text and context_text.strip():
        prompt_parts.append(f"Use the following context if relevant: {context_text}")

    prompt_parts.append("Break down your explanation into logical steps. Be clear and comprehensive. Use illustrative examples if helpful.")
    prompt = "\n\n".join(prompt_parts)

    logger.info(f"Requesting explanation for query: '{user_query[:100]}...'")
    explanation = get_llm_response(prompt, provider=provider, task_type='explain_complex')
    return explanation


# --- New Service Function for Question Generation ---
def generate_questions_from_text_with_llm(text_content, num_questions=3,
                                        question_types=['multiple_choice', 'short_answer'],
                                        provider=None):
    """
    Uses an LLM to generate a specified number of questions of given types from text content.
    Attempts to get structured output (e.g., JSON).
    """
    if not text_content or not text_content.strip():
        logger.warning("Question generation called with empty text content.")
        return {"error": "No text content provided for question generation."}

    question_type_str = ", ".join(question_types)

    prompt = f"""Given the following text, please generate {num_questions} exam questions.
The questions should be of the following types: {question_type_str}.

For each question, provide:
1. The question text.
2. The question type (e.g., 'multiple_choice', 'short_answer', 'essay').
3. For 'multiple_choice' questions, provide 3-4 options and indicate the correct answer key (e.g., A, B, C, D). Options should be a dictionary like {{"A": "Option A", "B": "Option B", "correct": "A"}}.
4. The difficulty level (e.g., 'easy', 'medium', 'hard'). This is optional but preferred.

Format the output as a JSON list of objects, where each object represents a question.
Example for a single multiple-choice question:
{{
  "question_text": "What is the capital of France?",
  "question_type": "multiple_choice",
  "options": {{ "A": "Berlin", "B": "Madrid", "C": "Paris", "D": "Rome", "correct": "C" }},
  "difficulty": "easy"
}}
Example for a single short_answer question:
{{
  "question_text": "Explain the concept of photosynthesis in one sentence.",
  "question_type": "short_answer",
  "difficulty": "medium"
}}

--- TEXT FOR QUESTION GENERATION ---
{text_content}
--- END OF TEXT ---

Provide ONLY the JSON list of questions as your response. Ensure the JSON is well-formed.
"""

    logger.info(f"Requesting {num_questions} questions of types '{question_type_str}' from text content (length: {len(text_content)}).")
    raw_response = get_llm_response(prompt, provider=provider, task_type='generate_questions')

    if raw_response is None or (isinstance(raw_response, str) and raw_response.startswith("Error:")):
        logger.error(f"LLM error during question generation: {raw_response}")
        return {"error": f"AI service error during question generation: {raw_response}"}

    try:
        # LLMs might sometimes include markdown backticks or "```json" prefix/suffix
        clean_response = raw_response.strip()
        if clean_response.startswith("```json"):
            clean_response = clean_response[len("```json"):] # Corrected slicing
        if clean_response.endswith("```"):
            clean_response = clean_response[:-len("```")] # Corrected slicing

        # Sometimes LLMs might still output text before/after JSON block, try to find JSON block
        json_start_index = clean_response.find('[')
        json_end_index = clean_response.rfind(']')
        if json_start_index != -1 and json_end_index != -1 and json_end_index > json_start_index:
            clean_response = clean_response[json_start_index : json_end_index+1]
        else: # If no clear list structure, try to find a dict structure (for single question)
            json_start_index = clean_response.find('{')
            json_end_index = clean_response.rfind('}')
            if json_start_index != -1 and json_end_index != -1 and json_end_index > json_start_index:
                 clean_response = clean_response[json_start_index : json_end_index+1]
                 # If it's a single dict, wrap it in a list for consistency
                 generated_questions = [json.loads(clean_response.strip())]
            else:
                raise json.JSONDecodeError("No valid JSON array or object found in LLM response.", clean_response, 0)


        if not isinstance(generated_questions, list): # Should be a list from the prompt
             # This path might be taken if single dict was loaded and wrapped above.
             # If it was already parsed into a list by json.loads, this check is fine.
             if isinstance(generated_questions, dict): # If it's a single dict, wrap it.
                 generated_questions = [generated_questions]
             else: # If not a list or a dict that we wrapped
                 raise ValueError("LLM did not return a list of questions or a single question object.")

        # Further validation of each question object can be added here
        # e.g., check for required fields: question_text, question_type
        # and for MCQs, options and options.correct
        valid_questions = []
        for q_data in generated_questions:
            if not isinstance(q_data, dict):
                logger.warning(f"Skipping non-dictionary item in generated questions list: {q_data}")
                continue
            if 'question_text' not in q_data or 'question_type' not in q_data:
                logger.warning(f"Skipping generated question due to missing required fields: {q_data}")
                continue
            if q_data['question_type'] == 'multiple_choice' and \
               (not isinstance(q_data.get('options'), dict) or 'correct' not in q_data['options']):
                logger.warning(f"Skipping generated MCQ due to invalid options: {q_data}")
                continue
            valid_questions.append(q_data)

        if not valid_questions:
            logger.warning(f"No valid questions found after parsing and validation. Raw response: '{raw_response}'")
            return {"error": "AI generated questions but they were not in the expected format or were incomplete.", "raw_response": raw_response}

        logger.info(f"Successfully generated and validated {len(valid_questions)} questions from text.")
        return {"questions": valid_questions}

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response from LLM for question generation: {e}. Raw response: '{raw_response}'", exc_info=True)
        return {"error": "Failed to parse AI-generated questions as valid JSON. Please try again or adjust the input text.", "raw_response": raw_response}
    except ValueError as e:
        logger.error(f"LLM response for question generation was not a list or valid structure: {e}. Raw response: '{raw_response}'", exc_info=True)
        return {"error": f"AI-generated questions format error: {e}. Please try again.", "raw_response": raw_response}
    except Exception as e:
        logger.error(f"Unexpected error processing LLM response for question generation: {e}. Raw response: '{raw_response}'", exc_info=True)
        return {"error": "An unexpected error occurred while processing generated questions.", "raw_response": raw_response}
