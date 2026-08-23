from pathlib import Path

import hashlib
import json
import re

import fitz

from langchain_core.documents import Document

from langchain_huggingface import (
    HuggingFaceEmbeddings
)

from langchain_community.vectorstores import (
    FAISS
)

from langchain_text_splitters import (
    RecursiveCharacterTextSplitter
)

from rank_bm25 import BM25Okapi


# =========================================================
# METADATA
# =========================================================

def get_metadata(
    filename
):

    name = filename.lower()

    metadata = {

        "source":
            filename,

        "type":
            "general_document",

        "status":
            "current",

        "customer":
            ""

    }


    # Deprecated

    if (
        "deprecated" in name
        or
        "v2_" in name
    ):

        metadata["status"] = (
            "deprecated"
        )


    # Northstar

    if "northstar" in name:

        metadata["type"] = (
            "customer_agreement"
        )

        metadata["customer"] = (
            "northstar logistics"
        )


    # LumenWorks

    if "lumenworks" in name:

        metadata["type"] = (
            "customer_agreement"
        )

        metadata["customer"] = (
            "lumenworks"
        )


    # Support policy

    if (
        "support_policy" in name
        and
        metadata["status"]
        !=
        "deprecated"
    ):

        metadata["type"] = (
            "current_policy"
        )


    # SOP

    if (
        "cancellation" in name
        or
        "service_credit" in name
    ):

        metadata["type"] = (
            "sop"
        )


    # Product documentation

    if "product_operations" in name:

        metadata["type"] = (
            "product_operations"
        )


    return metadata


# =========================================================
# HYBRID RETRIEVER
# =========================================================

class HybridRetriever:

    def __init__(
        self,
        documents,
        vectorstore
    ):

        self.documents = documents

        self.vectorstore = vectorstore


        self.tokens = [

            re.findall(

                r"\w+",

                document.page_content.lower()

            )

            for document
            in documents

        ]


        if self.tokens:

            self.bm25 = BM25Okapi(
                self.tokens
            )

        else:

            self.bm25 = None


    @property
    def document_count(self):

        return len(
            self.documents
        )


    # =====================================================
    # SEARCH
    # =====================================================

    def search(
        self,
        query,
        user_context,
        k=6
    ):

        if not self.documents:

            return json.dumps({

                "context":
                    "No documents are available.",

                "sources":
                    []

            })


        # -------------------------------------------------
        # ACCESS CONTROL
        # -------------------------------------------------

        allowed_indexes = []


        for index, document in enumerate(
            self.documents
        ):

            customer = (
                str(
                    document.metadata.get(
                        "customer",
                        ""
                    )
                )
                .lower()
            )


            # Internal user

            if user_context[
                "can_access_all_accounts"
            ]:

                allowed_indexes.append(
                    index
                )

                continue


            # Customer can see general
            # documents and own agreement

            user_account = (

                user_context[
                    "account_scope"
                ]
                .lower()
            )


            if (
                not customer
                or
                customer == user_account
            ):

                allowed_indexes.append(
                    index
                )


        # -------------------------------------------------
        # DENSE SEARCH
        # -------------------------------------------------

        dense_results = (

            self.vectorstore
            .similarity_search(
                query,
                k=10
            )

        )


        dense_ids = {

            id(document)

            for document
            in dense_results

        }


        # -------------------------------------------------
        # BM25 SEARCH
        # -------------------------------------------------

        sparse_results = []


        if self.bm25:

            query_tokens = re.findall(

                r"\w+",

                query.lower()

            )


            scores = self.bm25.get_scores(
                query_tokens
            )


            sparse_results = sorted(

                range(
                    len(scores)
                ),

                key=lambda index:
                    scores[index],

                reverse=True

            )[:10]


        # -------------------------------------------------
        # COMBINE RESULTS
        # -------------------------------------------------

        candidates = []


        for document in dense_results:

            for index in allowed_indexes:

                if (
                    self.documents[index]
                    is document
                ):

                    if document not in candidates:

                        candidates.append(
                            document
                        )


        for index in sparse_results:

            if index in allowed_indexes:

                document = (
                    self.documents[index]
                )

                if document not in candidates:

                    candidates.append(
                        document
                    )


        # -------------------------------------------------
        # SOURCE PRIORITY
        # -------------------------------------------------

        def priority(
            document
        ):

            metadata = (
                document.metadata
            )

            score = 0


            if (
                metadata.get("status")
                ==
                "current"
            ):

                score += 30


            if (
                metadata.get("status")
                ==
                "deprecated"
            ):

                score -= 50


            if (
                metadata.get("type")
                ==
                "customer_agreement"
            ):

                score += 50


            if (
                metadata.get("type")
                ==
                "current_policy"
            ):

                score += 30


            if (
                metadata.get("type")
                ==
                "sop"
            ):

                score += 25


            return score


        candidates = sorted(

            candidates,

            key=priority,

            reverse=True

        )[:k]


        # -------------------------------------------------
        # BUILD CONTEXT
        # -------------------------------------------------

        contexts = []

        sources = []


        for document in candidates:

            metadata = (
                document.metadata
            )


            contexts.append(

                f"""
SOURCE:
{metadata.get("source")}

TYPE:
{metadata.get("type")}

STATUS:
{metadata.get("status")}

PAGE:
{metadata.get("page")}

CONTENT:

{document.page_content}
"""

            )


            sources.append({

                "source":
                    metadata.get(
                        "source"
                    ),

                "type":
                    metadata.get(
                        "type"
                    ),

                "status":
                    metadata.get(
                        "status"
                    ),

                "page":
                    metadata.get(
                        "page"
                    )

            })


        return json.dumps({

            "context":
                "\n\n---\n\n".join(
                    contexts
                ),

            "sources":
                sources

        })


# =========================================================
# BUILD / LOAD INDEX
# =========================================================

def build_or_load_retriever(
    document_directory,
    storage_directory
):

    document_directory = Path(
        document_directory
    )

    storage_directory = Path(
        storage_directory
    )


    storage_directory.mkdir(
        parents=True,
        exist_ok=True
    )


    pdf_files = sorted(

        document_directory.rglob(
            "*.pdf"
        )

    )


    if not pdf_files:

        return HybridRetriever(

            [],

            EmptyVectorStore()

        )


    # -----------------------------------------------------
    # INDEX SIGNATURE
    # -----------------------------------------------------

    signature_text = ""

    for pdf in pdf_files:

        signature_text += (

            f"{pdf.name}:"
            f"{pdf.stat().st_mtime_ns}"

        )


    signature = hashlib.md5(

        signature_text.encode()

    ).hexdigest()


    metadata_file = (

        storage_directory
        /
        f"index_{signature}.json"

    )


    faiss_directory = (

        storage_directory
        /
        f"faiss_{signature}"

    )


    # -----------------------------------------------------
    # LOAD EXISTING
    # -----------------------------------------------------

    if (
        metadata_file.exists()
        and
        faiss_directory.exists()
    ):

        data = json.loads(

            metadata_file.read_text(
                encoding="utf-8"
            )

        )


        documents = [

            Document(

                page_content=
                    item["content"],

                metadata=
                    item["metadata"]

            )

            for item in data

        ]


        embeddings = HuggingFaceEmbeddings(

            model_name=
                "sentence-transformers/all-MiniLM-L6-v2"

        )


        vectorstore = FAISS.load_local(

            str(faiss_directory),

            embeddings,

            allow_dangerous_deserialization=True

        )


        return HybridRetriever(

            documents,

            vectorstore

        )


    # -----------------------------------------------------
    # CREATE DOCUMENTS
    # -----------------------------------------------------

    splitter = RecursiveCharacterTextSplitter(

        chunk_size=1000,

        chunk_overlap=150

    )


    documents = []


    for pdf_file in pdf_files:

        metadata = get_metadata(
            pdf_file.name
        )


        pdf = fitz.open(
            pdf_file
        )


        for page_number, page in enumerate(

            pdf,

            start=1

        ):

            text = page.get_text(
                "text"
            )


            if not text.strip():

                continue


            chunks = splitter.split_text(
                text
            )


            for chunk in chunks:

                page_metadata = (
                    metadata.copy()
                )


                page_metadata["page"] = (
                    page_number
                )


                documents.append(

                    Document(

                        page_content=
                            chunk,

                        metadata=
                            page_metadata

                    )

                )


    # -----------------------------------------------------
    # EMBEDDINGS
    # -----------------------------------------------------

    embeddings = HuggingFaceEmbeddings(

        model_name=
            "sentence-transformers/all-MiniLM-L6-v2"

    )


    # -----------------------------------------------------
    # FAISS
    # -----------------------------------------------------

    vectorstore = FAISS.from_documents(

        documents,

        embeddings

    )


    vectorstore.save_local(

        str(faiss_directory)

    )


    # -----------------------------------------------------
    # SAVE METADATA
    # -----------------------------------------------------

    metadata_file.write_text(

        json.dumps(

            [

                {

                    "content":
                        document.page_content,

                    "metadata":
                        document.metadata

                }

                for document
                in documents

            ]

        ),

        encoding="utf-8"

    )


    return HybridRetriever(

        documents,

        vectorstore

    )


# =========================================================
# EMPTY VECTOR STORE
# =========================================================

class EmptyVectorStore:

    def similarity_search(
        self,
        *args,
        **kwargs
    ):

        return []