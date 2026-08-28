"""Three sections sitting the same paper: 108 students, none repeated.

The teacher in the demo teaches three sections of the same course, so the exam
is identical and the rosters are not. Names live apart from the rendering logic
because they are data, and because a duplicate here would collide in the SIS
ledger where student_id is the key.
"""

SECTION_A_NAMES: tuple[str, ...] = (
    "Alejandra Bermudez", "Bruno Salazar", "Carolina Peralta", "Damian Ochoa",
    "Elisa Montoya", "Facundo Larrea", "Gabriela Arrieta", "Hugo Belmonte",
    "Irene Calderon", "Joaquin Estevez", "Karla Villalba", "Leandro Prieto",
    "Marisol Aguirre", "Nestor Caballero", "Olivia Zambrano", "Patricio Rueda",
    "Quintin Alfaro", "Rocio Betancur", "Samuel Escalante", "Tamara Nieto",
    "Ulises Palacios", "Valeria Cifuentes", "Wilmer Toledo", "Ximena Bustos",
    "Yamil Cordero", "Zoe Barrantes", "Adrian Melgar", "Bianca Rosales",
    "Cristobal Duarte", "Delia Sandoval", "Emiliano Cuellar", "Fernanda Loaiza",
    "Gonzalo Trevino", "Helena Bracho", "Ignacio Robledo", "Julieta Camargo",
)

SECTION_B_NAMES: tuple[str, ...] = (
    "Amanda Riquelme", "Baltasar Nunez", "Constanza Vergara", "Diego Maldonado",
    "Estefania Pinilla", "Federico Anzola", "Graciela Otero", "Horacio Bermejo",
    "Ivana Solorzano", "Jeronimo Pacheco", "Katia Lozano", "Lorenzo Mejia",
    "Micaela Ferrer", "Nicanor Osuna", "Ofelia Granados", "Pablo Cervantes",
    "Rafaela Quintana", "Salvador Iriarte", "Teresa Almeida", "Ubaldo Ferreira",
    "Vicente Alcocer", "Wanda Segura", "Xavier Bonilla", "Yolanda Peraza",
    "Zacarias Mora", "Antonella Guzman", "Benjamin Tapia", "Clarisa Uribe",
    "Dario Villamil", "Eugenia Sepulveda", "Fabricio Correa", "Gisela Andrade",
    "Hernan Rivadeneira", "Isadora Lemus", "Javier Encinas", "Ludmila Parodi",
)

SECTION_C_NAMES: tuple[str, ...] = (
    "Agustina Ferrari", "Bernardo Quiroga", "Celeste Miranda", "Domingo Ayala",
    "Elvira Zapata", "Fausto Berrio", "Guadalupe Nino", "Hector Villarreal",
    "Ines Carvajal", "Jacinto Morales", "Kiara Espinal", "Lautaro Benavides",
    "Magdalena Ruiz", "Nahuel Ibarra", "Octavia Del Valle", "Prudencio Gaitan",
    "Renata Solano", "Sebastiana Roldan", "Timoteo Aparicio", "Urania Meneses",
    "Victor Manrique", "Wendy Chaparro", "Xiomara Delgadillo", "Yago Restrepo",
    "Zulema Pineda", "Ariadna Cortes", "Bautista Naranjo", "Cecilia Verdugo",
    "Dante Aroca", "Emilia Zuluaga", "Franco Bustamante", "Georgina Alzate",
    "Hipolito Meza", "Ivonne Pastrana", "Joel Santacruz", "Luciana Ferreyra",
)

SECTION_NAMES: dict[str, tuple[str, ...]] = {
    "10A": SECTION_A_NAMES,
    "10B": SECTION_B_NAMES,
    "10C": SECTION_C_NAMES,
}
