import dotenv

dotenv.load_dotenv()

from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_mistralai import ChatMistralAI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableParallel

from langchain_core.pydantic_v1 import BaseModel, Field
import json
import concurrent.futures
import hashlib

MODEL_PATH = 'model.json'
with open(MODEL_PATH, 'r', encoding='utf-8') as file:
    data = json.load(file)

models = {}
for category in data.values():
    for model_name in category:
        modified_model_name = '_'.join(model_name.split('_')[1:])
        models[modified_model_name] = ChatGroq(model=modified_model_name)

prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "A theme is given, and you need to provide subcategories that are related to the main theme.",
        ),
        ("human", "Give 8-10 subcategories of the following main theme:  {text}"),
    ]
)

prompt_data_generation = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a synthetic data generator. Your task is to generate a dataset based on a given theme and category. 
       Create 5-6 questions within the specified category, ensuring they gradually increase in complexity. The last question should be very challenging.""",
        ),
        ("human", "Generate a synthetic dataset with the following theme: {text}"),
    ]
)


class SubCategories(BaseModel):
    subcategories: list[str] = Field(description="Names of the subcategories")


class DatasetExample(BaseModel):
    prompt: str = Field(
        description="The question to ask, or the function signature to complete"
    )
    answer: str = Field(description="The answer to the question")


class DatasetExamples(BaseModel):
    examples: list[DatasetExample] = Field(description="List of examples")


class FinalDatasetExemple(BaseModel):
    prompt: str
    chosen: str
    rejected: str


def generate_rejected(prompts: list[str], student_model: BaseChatModel):
    rejected = []
    runnables = {
        f"{i}": (ChatPromptTemplate.from_template(prompt) | student_model)
        for i, prompt in enumerate(prompts)
    }
    map_chain = RunnableParallel(**runnables)  # type: ignore
    outputs = map_chain.invoke({})
    rejected = [output.content for output in outputs.values()]
    return rejected


def generate_category(
    theme: str,
    category: str,
    dataset: list[FinalDatasetExemple],
    oracle_model: BaseChatModel,
    student_model: BaseChatModel,
):

    runnable_dataset_generation = (
        prompt_data_generation
        | oracle_model.with_structured_output(schema=DatasetExamples)
    )
    try:
        generated_examples: DatasetExamples = runnable_dataset_generation.invoke(
            {"text": f"Theme: {theme}, Category: {category}"}
        )  # type: ignore
        generated_examples: DatasetExamples = runnable_dataset_generation.invoke({"text": f"Theme: {theme}, Category: {category}"})  # type: ignore
        rejecteds = generate_rejected(
            [example.prompt for example in generated_examples.examples], student_model
        )
        for example, rejected in zip(generated_examples.examples, rejecteds):
            dataset.append(
                FinalDatasetExemple(
                    prompt=example.prompt,
                    chosen=example.answer,
                    rejected=rejected,  # type: ignore
                )
            )
        print(f"Generated dataset for category: {category}")
    except Exception as e:

        print(f"Failed to generate dataset for category: {category}, Error: {e}")


def generate_dataset(
    theme: str, oracle_model_id: str, student_model_id: str
) -> list[FinalDatasetExemple]:
    oracle_model = models[oracle_model_id]
    student_model = models[student_model_id]
    runnable = prompt | oracle_model.with_structured_output(schema=SubCategories)
    categories: SubCategories = runnable.invoke({"text": theme})  # type: ignore
    print(categories.subcategories)
    dataset: list[FinalDatasetExemple] = []
    for category in categories.subcategories:
        print("Generating dataset for category: ", category)
        generate_category(theme, category, dataset, oracle_model, student_model)
    # def worker(category):
    #     return generate_category(theme, category, dataset, large_model, small_model)
    # with concurrent.futures.ThreadPoolExecutor() as executor:
    #         executor.map(worker, categories.subcategories)

    return dataset


def dump_dataset(
    dataset: list[FinalDatasetExemple], oracle_model_id: str, student_model_id: str
) -> str:
    final_dataset = json.dumps(
        [{"id": i} | example.dict() for i, example in enumerate(dataset)], indent=4
    )
    # Generate a hash of the final dataset
    dataset_hash = hashlib.sha256(final_dataset.encode()).hexdigest()
    dataset_uuid = dataset_hash[:32]
    dataset_file_path = (
        f"datasets/{oracle_model_id}_{student_model_id}_{dataset_uuid}.json"
    )
    with open(dataset_file_path, "w") as f:
        f.write(final_dataset)
        f.close()
    return dataset_file_path


def create_dataset(theme, oracle_model_id, student_model_id):
    dataset = generate_dataset(theme, oracle_model_id, student_model_id)
    return dump_dataset(dataset, oracle_model_id, student_model_id)


if __name__ == "__main__":
    theme = "Function Implementation of DataStructre and Algorithms in Python"
    path = create_dataset(theme,"groq_mixtral-8x7b-32768", "groq_gemma-7b-it")
    print(path)